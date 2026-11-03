from __future__ import annotations

import logging
import time
from functools import lru_cache

import httpx
import numpy as np
from django.conf import settings

from api.embeddings import as_query_vector

logger = logging.getLogger(__name__)

#: Inputs per request to the provider; sized for its per-request limit.
BATCH_SIZE = 32

#: Attempts for a transiently failing request, including the first.
MAX_ATTEMPTS = 3

#: Base delay for the retry backoff, in seconds. Exponential from here.
RETRY_BASE_SECONDS = 0.5

#: Never wait longer than this between attempts, however many have failed.
RETRY_MAX_SECONDS = 8.0

#: Passage vs query embeddings differ only in the prefix they carry.
KIND_QUERY = "query"
KIND_PASSAGE = "passage"

#: The one model this deployment embeds with; the id it carries at Cloudflare.
SUPPORTED_MODEL = "BAAI/bge-small-en-v1.5"
SUPPORTED_MODEL_CLOUDFLARE_ID = "@cf/baai/bge-small-en-v1.5"

#: Cloudflare's code for the free allocation being spent; blocks until 00:00 UTC.
QUOTA_ERROR_CODE = 4006


class EmbeddingError(Exception):
    def __init__(self, reason: str, *, retryable: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


def embed_texts(texts: list[str]) -> list[list[float]]:
    return _embed(texts, KIND_PASSAGE)


def embed_query(text: str) -> list[float]:
    vectors = _embed([text], KIND_QUERY)
    if not vectors:
        raise EmbeddingError("The embedding provider returned nothing for the query.")
    return vectors[0]


def _embed(texts: list[str], kind: str) -> list[list[float]]:
    if not texts:
        return []

    if settings.EMBED_MODEL != SUPPORTED_MODEL:
        raise EmbeddingError(
            f"the stored vectors were indexed with {SUPPORTED_MODEL}; "
            f"EMBED_MODEL is {settings.EMBED_MODEL}",
            retryable=False,
        )

    account_id, token = _cloudflare_config()
    endpoint = _cloudflare_endpoint(account_id)
    prefix = settings.EMBEDDING_QUERY_PREFIX if kind == KIND_QUERY else ""
    prepared = [f"{prefix}{text}" for text in texts]

    # Batches of BATCH_SIZE; results extend in input order.
    vectors: list[list[float]] = []
    for offset in range(0, len(prepared), BATCH_SIZE):
        batch = prepared[offset : offset + BATCH_SIZE]
        vectors.extend(_cloudflare_request(endpoint, token, batch))

    expected = settings.EMBEDDING_DIM
    for index, vector in enumerate(vectors):
        if len(vector) != expected:
            # A wrong width reads later as a Postgres column mismatch; name it here.
            raise EmbeddingError(
                f"the embedding provider returned {len(vector)} dimensions for "
                f"input {index} but EMBEDDING_DIM is {expected}; "
                f"{settings.EMBED_MODEL} may not be the model this project expects",
                retryable=False,
            )

    return vectors


def _cloudflare_config() -> tuple[str, str]:
    account_id = settings.CLOUDFLARE_ACCOUNT_ID
    token = settings.CLOUDFLARE_API_TOKEN
    if not account_id or not token:
        raise EmbeddingError(
            "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are not configured.",
            retryable=False,
        )
    return account_id, token


def _cloudflare_endpoint(account_id: str) -> str:
    base = settings.CLOUDFLARE_BASE_URL.rstrip("/")
    return f"{base}/accounts/{account_id}/ai/run/{SUPPORTED_MODEL_CLOUDFLARE_ID}"


@lru_cache(maxsize=1)
def _cloudflare_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(settings.SUPABASE_AUTH_TIMEOUT_SECONDS * 6, connect=10.0)
    )


def reset_client_cache() -> None:
    _cloudflare_client.cache_clear()


def _cloudflare_request(endpoint: str, token: str, texts: list[str]) -> list[list[float]]:
    # pooling:"cls" plus normalisation keeps vectors interchangeable with stored ones.
    payload = {"text": texts, "pooling": "cls"}

    last_error: str | None = None

    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            time.sleep(_backoff(attempt))

        try:
            response = _cloudflare_client().post(
                endpoint,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            # A transport failure is our network or theirs; both retry.
            last_error = str(exc)
            logger.warning("Embedding request failed to send (attempt %d): %s", attempt + 1, exc)
            continue

        try:
            body = response.json()
        except ValueError as exc:
            raise EmbeddingError(
                "the embedding provider returned a malformed response", retryable=True
            ) from exc
        if not isinstance(body, dict):
            raise EmbeddingError(
                "the embedding provider returned a malformed response", retryable=True
            )

        code, message = _cloudflare_error(body)
        if code == QUOTA_ERROR_CODE or "free allocation" in message.lower():
            raise _cloudflare_quota_error()

        if response.status_code == 429 or response.status_code >= 500:
            # Rate limited or their fault. Retryable by definition.
            last_error = f"the provider returned {response.status_code}"
            logger.warning(
                "Embedding provider returned %d (attempt %d)",
                response.status_code,
                attempt + 1,
            )
            continue

        if 200 <= response.status_code < 300:
            if body.get("success") is not False:
                return _parse_cloudflare_response(body, len(texts))

            # Some model failures arrive inside a 200; still transient.
            last_error = f"the model failed (code {code}): {message}"
            logger.warning("Embedding model failed (attempt %d): %s", attempt + 1, last_error)
            continue

        if response.status_code in (401, 403):
            raise EmbeddingError(
                f"Cloudflare rejected the credentials ({response.status_code}); "
                "check CLOUDFLARE_API_TOKEN",
                retryable=False,
            )

        # Other 4xx is a wrong request; retrying would send it again.
        raise EmbeddingError(
            f"the embedding provider rejected the request ({response.status_code}"
            + (f", code {code}" if code is not None else "")
            + "); check CLOUDFLARE_ACCOUNT_ID and the Workers AI model id",
            retryable=False,
        )

    raise EmbeddingError(
        f"the embedding provider could not be reached after {MAX_ATTEMPTS} attempts"
        + (f": {last_error}" if last_error else ""),
        retryable=True,
    )


def _parse_cloudflare_response(body: dict, expected: int) -> list[list[float]]:
    result = body.get("result")
    rows = result.get("data") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        raise EmbeddingError(
            "the embedding provider returned no data array", retryable=True
        )

    # `data` binds to `text` positionally; no input index comes back.
    if len(rows) != expected:
        raise EmbeddingError(
            f"the embedding provider returned {len(rows)} vectors for "
            f"{expected} inputs",
            retryable=True,
        )

    try:
        vectors = np.asarray(rows, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise EmbeddingError(
            "the embedding provider returned a row without a vector", retryable=True
        ) from exc

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    # A zero norm has no direction; divide by 1 to keep the arithmetic defined.
    norms[norms == 0.0] = 1.0
    return [as_query_vector(vector) for vector in vectors / norms]


def _cloudflare_error(body: dict) -> tuple[int | None, str]:
    # Failures are {"success": false, "errors": [...]}; sometimes inside a 2xx.
    if not isinstance(body, dict) or body.get("success") is not False:
        return None, ""
    errors = body.get("errors")
    if not (isinstance(errors, list) and errors and isinstance(errors[0], dict)):
        return None, ""
    code = errors[0].get("code")
    try:
        code = None if code is None else int(code)
    except (TypeError, ValueError):
        return None, str(errors[0].get("message", ""))
    return code, str(errors[0].get("message", ""))


def _cloudflare_quota_error() -> EmbeddingError:
    return EmbeddingError(
        "The embedding service's free daily quota was used up. New "
        "attempts fail until it resets at 00:00 UTC; this document can be "
        "re-ingested after that.",
        retryable=False,
    )


def _backoff(attempt: int) -> float:
    return min(RETRY_BASE_SECONDS * (2 ** (attempt - 1)), RETRY_MAX_SECONDS)
