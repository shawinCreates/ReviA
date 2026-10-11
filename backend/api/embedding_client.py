from __future__ import annotations

import logging
import time
from functools import lru_cache

import httpx
from django.conf import settings

from api.embeddings import as_query_vector, check_embeddings_are_comparable

logger = logging.getLogger(__name__)

#: Inputs per request to a hosted provider. Sized to stay under its per-request
#: limit while keeping the request count low for a large document.
BATCH_SIZE = 32

#: Attempts for a rate-limited or transiently failing request, including the
#: first. Three is enough to ride out a burst without holding a worker.
MAX_ATTEMPTS = 3

#: Base delay for the retry backoff, in seconds. Exponential from here.
RETRY_BASE_SECONDS = 0.5

#: Never wait longer than this between attempts, however many have failed.
RETRY_MAX_SECONDS = 8.0

#: The input kinds, and what a hosted provider calls them.
KIND_QUERY = "query"
KIND_PASSAGE = "passage"


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

    check_embeddings_are_comparable(settings.EMBED_MODEL)

    provider = settings.EMBEDDING_PROVIDER
    if provider == "local":
        vectors = _embed_local(texts, kind)
    elif provider == "nvidia":
        vectors = _embed_nvidia(texts, kind)
    else:
        raise EmbeddingError(
            f"EMBEDDING_PROVIDER is {provider!r}; expected 'local' or 'nvidia'.",
            retryable=False,
        )

    expected = settings.EMBEDDING_DIM
    for index, vector in enumerate(vectors):
        if len(vector) != expected:
            # Caught here rather than at insert time, where Postgres would
            # report a generic dimension mismatch against the column.
            raise EmbeddingError(
                f"the embedding provider returned {len(vector)} dimensions for "
                f"input {index} but EMBEDDING_DIM is {expected}; "
                f"{settings.EMBED_MODEL} may not be the model this project expects",
                retryable=False,
            )

    return vectors

# --- local provider ------------------------------------------------------------


@lru_cache(maxsize=1)
def _local_model():
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise EmbeddingError(
            "EMBEDDING_PROVIDER is 'local' but fastembed is not installed; "
            "run `uv sync`, or set EMBEDDING_PROVIDER to 'nvidia'",
            retryable=False,
        ) from exc

    logger.info("Loading the local embedding model %s", settings.EMBED_MODEL)
    try:
        return TextEmbedding(
            settings.EMBED_MODEL, cache_dir=settings.EMBEDDING_CACHE_DIR or None
        )
    except Exception as exc:
        # Most often the model cannot be downloaded on first run. Saying so is
        # more useful than the library's own error, which does not mention that
        # it needs the network once.
        raise EmbeddingError(
            f"the local embedding model {settings.EMBED_MODEL!r} could not be "
            f"loaded ({type(exc).__name__}); it is downloaded on first use and "
            f"needs network access, or set EMBEDDING_CACHE_DIR to a prepared copy",
            retryable=False,
        ) from exc


def reset_client_cache() -> None:
    _local_model.cache_clear()
    _nvidia_client.cache_clear()


def _embed_local(texts: list[str], kind: str) -> list[list[float]]:
    model = _local_model()
    prefix = settings.EMBEDDING_QUERY_PREFIX if kind == KIND_QUERY else ""
    prepared = [f"{prefix}{text}" for text in texts]

    try:
        vectors = [as_query_vector(vector) for vector in model.embed(prepared)]
    except EmbeddingError:
        raise
    except Exception as exc:
        raise EmbeddingError(
            f"the local embedding model failed ({type(exc).__name__})",
            retryable=False,
        ) from exc

    if len(vectors) != len(prepared):
        # A local model that returns the wrong count is a bug worth surfacing
        # rather than pairing off positionally, which would silently misalign
        # every vector after the first.
        raise EmbeddingError(
            f"the local embedding model returned {len(vectors)} vectors for "
            f"{len(prepared)} inputs",
            retryable=False,
        )

    return vectors

# --- hosted provider -----------------------------------------------------------


def _nvidia_key() -> str:
    key = settings.NVIDIA_API_KEY
    if not key:
        raise EmbeddingError(
            "EMBEDDING_PROVIDER is 'nvidia' but no key is configured "
            "(set NVIDIA_API_KEY).",
            retryable=False,
        )
    return key


def _nvidia_endpoint() -> str:
    return f"{settings.NVIDIA_BASE_URL.rstrip('/')}/embeddings"


@lru_cache(maxsize=1)
def _nvidia_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(settings.SUPABASE_AUTH_TIMEOUT_SECONDS * 6, connect=10.0)
    )


def _embed_nvidia(texts: list[str], kind: str) -> list[list[float]]:
    payload = {
        "model": settings.EMBED_MODEL,
        "input": texts,
        "encoding_format": "float",
        "input_type": kind,
        "truncate": "END",
    }

    last_error: str | None = None

    for attempt in range(MAX_ATTEMPTS):
        if attempt:
            time.sleep(_backoff(attempt))

        try:
            response = _nvidia_client().post(
                _nvidia_endpoint(),
                json=payload,
                headers={
                    "Authorization": f"Bearer {_nvidia_key()}",
                    "Accept": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            # A transport failure is our network or theirs; both are worth
            # retrying, and neither says anything about the request.
            last_error = str(exc)
            logger.warning(
                "Embedding request failed to send (attempt %d): %s", attempt + 1, exc
            )
            continue

        if response.status_code == 429 or response.status_code >= 500:
            # Rate limited or their fault. Retryable by definition.
            last_error = f"the provider returned {response.status_code}"
            logger.warning(
                "Embedding provider returned %d (attempt %d)",
                response.status_code,
                attempt + 1,
            )
            continue

        if response.status_code in (404, 410):
            # The model is not available to this account. Every retry fails the
            # same way, and the two codes together are what a retired model
            # looks like, so this says so rather than reporting a bare status.
            raise EmbeddingError(
                f"the embedding provider does not offer {settings.EMBED_MODEL} "
                f"({response.status_code}); the model may have been retired, or "
                f"this account may not have access to embeddings",
                retryable=False,
            )

        if response.status_code != 200:
            # Other 4xx means the request itself is wrong. Retrying sends the
            # same wrong request again.
            raise EmbeddingError(
                f"the embedding provider rejected the request "
                f"({response.status_code}); check EMBED_MODEL and the API key",
                retryable=False,
            )

        return _parse_nvidia_response(response, len(texts))

    raise EmbeddingError(
        f"the embedding provider could not be reached after {MAX_ATTEMPTS} attempts"
        + (f": {last_error}" if last_error else ""),
        retryable=True,
    )


def _parse_nvidia_response(response: httpx.Response, expected: int) -> list[list[float]]:
    try:
        body = response.json()
    except ValueError as exc:
        raise EmbeddingError(
            "the embedding provider returned a malformed response", retryable=True
        ) from exc

    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise EmbeddingError(
            "the embedding provider returned no data array", retryable=True
        )

    # The API documents an `index` per row because results may arrive out of
    # order. Sorting by it is what makes the positional contract hold; assuming
    # the array is already ordered is how embeddings end up attached to the wrong
    # text.
    indexed = []
    for position, row in enumerate(rows):
        if not isinstance(row, dict) or "embedding" not in row:
            raise EmbeddingError(
                "the embedding provider returned a row without a vector", retryable=True
            )
        index = row.get("index")
        indexed.append((position if index is None else int(index), row["embedding"]))

    indexed.sort(key=lambda pair: pair[0])
    vectors = [as_query_vector(row) for _, row in indexed]

    if len(vectors) != expected:
        raise EmbeddingError(
            f"the embedding provider returned {len(vectors)} vectors for "
            f"{expected} inputs",
            retryable=True,
        )

    return vectors


def _backoff(attempt: int) -> float:
    return min(RETRY_BASE_SECONDS * (2 ** (attempt - 1)), RETRY_MAX_SECONDS)
