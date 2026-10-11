from __future__ import annotations

import logging

import numpy as np
from django.conf import settings

logger = logging.getLogger(__name__)


def embedding_dimensions() -> int:
    return settings.EMBEDDING_DIM


def as_query_vector(embedding) -> list[float]:
    array = np.asarray(embedding, dtype=np.float32).reshape(-1)
    return array.tolist()


def check_query_vector(vector: list[float]) -> None:
    expected = embedding_dimensions()
    actual = len(vector)
    if actual != expected:
        raise ValueError(
            f"query vector has {actual} dimensions but the database stores "
            f"{expected}; {settings.EMBED_MODEL} is configured as the embedding "
            f"model, so either the model or EMBEDDING_DIM is wrong"
        )


def check_embeddings_are_comparable(model: str) -> None:
    if model != settings.EMBED_MODEL:
        raise ValueError(
            f"embeddings were produced with {model} but the database was set up "
            f"for {settings.EMBED_MODEL}; re-embed every stored chunk before "
            f"mixing them"
        )
