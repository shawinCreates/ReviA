"""Reading a chunk vector from a Django connection into a plain list.

Retrieval needs a query vector, and the one thing that is easy to get wrong
here is silently comparing the wrong thing. The embedding client and the
database have to agree on the model and the width, because two different models
produce vectors that are not comparable even at identical dimensions — the
distance would be computed, would look plausible, and would return nonsense.

These helpers make that agreement checkable at the call site rather than
something a reader has to remember.
"""

from __future__ import annotations

import logging

import numpy as np
from django.conf import settings

logger = logging.getLogger(__name__)


def embedding_dimensions() -> int:
    """The configured vector width.

    Named rather than reaching for `settings.EMBEDDING_DIM` at each call site so
    the check below has one thing to compare against.
    """
    return settings.EMBEDDING_DIM


def as_query_vector(embedding) -> list[float]:
    """Turn a client-produced embedding into something psycopg will accept.

    pgvector accepts a numpy array or a list, but a list built by the embedding
    client may be any sequence, and a nested list produces a database error
    that says nothing useful. Normalising here means the error you get is about
    the dimension, which is the actual problem when it happens.
    """
    array = np.asarray(embedding, dtype=np.float32).reshape(-1)
    return array.tolist()


def check_query_vector(vector: list[float]) -> None:
    """Raise if a query vector cannot be compared with the stored chunks.

    A wrong width is the failure this exists to catch, and Postgres reports it
    as a generic "expected 384 dimensions, not 768" from inside the operator —
    far from the code that produced the vector.
    """
    expected = embedding_dimensions()
    actual = len(vector)
    if actual != expected:
        raise ValueError(
            f"query vector has {actual} dimensions but the database stores "
            f"{expected}; {settings.EMBED_MODEL} is configured as the embedding "
            f"model, so either the model or EMBEDDING_DIM is wrong"
        )


def check_embeddings_are_comparable(model: str) -> None:
    """Guard against embeddings from a different model being mixed in.

    Cheap to state and impossible for the database to notice: every chunk could
    have a plausible width and still be from a model that was never meant to be
    compared with the others. Stored chunks carry no model tag yet, so this is
    the place a caller has to confirm before querying.
    """
    if model != settings.EMBED_MODEL:
        raise ValueError(
            f"embeddings were produced with {model} but the database was set up "
            f"for {settings.EMBED_MODEL}; re-embed every stored chunk before "
            f"mixing them"
        )
