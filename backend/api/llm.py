"""
LLM access.

One OpenAI-compatible client, two base_urls. Groq for generation, Cloudflare
Workers AI for bge-m3 embeddings. Nothing else in the codebase constructs a
vendor client, so swapping a provider is a base_url change. See
architecture.md.

Note that Cloudflare is configured but not exercised in phase 0: the account
does not exist yet. The base_url is derived here so that adding a key is the
only remaining step. See PROGRESS.md.
"""

from __future__ import annotations

import logging

from django.conf import settings
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_groq_client: AsyncOpenAI | None = None
_embed_client: AsyncOpenAI | None = None


def get_groq_client() -> AsyncOpenAI:
    """Groq, for generation. Async, because SSE must not block the worker."""
    global _groq_client
    if _groq_client is None:
        if not settings.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set.")
        _groq_client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY, base_url=settings.GROQ_BASE_URL
        )
        logger.info("Groq client ready, model=%s", settings.GROQ_MODEL)
    return _groq_client


def get_embed_client() -> AsyncOpenAI:
    """Cloudflare Workers AI, for bge-m3. Same client, different base_url."""
    global _embed_client
    if _embed_client is None:
        if not settings.CF_API_KEY or not settings.CF_BASE_URL:
            raise RuntimeError("CF_API_KEY and CF_ACCOUNT_ID are not set.")
        _embed_client = AsyncOpenAI(
            api_key=settings.CF_API_KEY, base_url=settings.CF_BASE_URL
        )
        logger.info("Cloudflare embed client ready, model=%s", settings.CF_EMBED_MODEL)
    return _embed_client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a batch of texts. Asserts the dimension on every response.

    The assertion is not defensive noise. A wrong dimension is a silent index
    error that surfaces weeks later as bad recall, with no obvious cause. See
    phases/phase-1-upload-and-parse.md.
    """
    from .models import EMBEDDING_DIM

    client = get_embed_client()
    response = await client.embeddings.create(
        model=settings.CF_EMBED_MODEL, input=texts
    )

    vectors = [item.embedding for item in response.data]
    for index, vector in enumerate(vectors):
        if len(vector) != EMBEDDING_DIM:
            raise ValueError(
                f"Embedding {index} has dimension {len(vector)}, expected "
                f"{EMBEDDING_DIM}. Refusing to write it: the vector index is "
                f"declared vector({EMBEDDING_DIM}) and a mismatch is a silent "
                f"retrieval bug."
            )
    return vectors
