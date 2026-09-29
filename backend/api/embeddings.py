"""
Local embeddings via ONNX Runtime.

Replaces the Cloudflare Workers AI plan. The reason is measured, not stylistic:
see fixtures/bench_embeddings.py. On a 512MB Render Free instance, `torch` alone
is 489MB and `sentence-transformers` is 854MB, so the usual HuggingFace stack
cannot run there at all. ONNX Runtime plus the pure-Rust `tokenizers` library is
274MB with working retrieval, and neither imports torch.

The trade-off accepted: bge-small-en-v1.5 is **English only**. A document
containing other languages will embed poorly. That is recorded in
architecture.md and risks.md rather than hidden, and switching to a multilingual
model later is a config change plus a re-embed.
"""

from __future__ import annotations

import logging
import threading

import numpy as np
from django.conf import settings

logger = logging.getLogger(__name__)

# Long inputs are truncated to this many tokens. bge-small's positional
# embeddings top out at 512, so going further is not possible anyway.
MAX_SEQUENCE_TOKENS = 512

_tokenizer = None
_session = None
_load_lock = threading.Lock()


def _build():
    """
    Construct the tokenizer and session lazily.

    Eagerly, this would add ~270MB to every management command, every test
    process, and every WSGI/ASGI worker even when nothing embeds anything.
    """
    from huggingface_hub import hf_hub_download
    from onnxruntime import InferenceSession
    from tokenizers import Tokenizer

    model_name = settings.EMBED_MODEL
    tokenizer = Tokenizer.from_pretrained(model_name)
    # from_pretrained looks for tokenizer.json, which bge repos do not ship;
    # the HF repo is loaded through sentence-transformers-style files instead.
    if tokenizer is None:  # pragma: no cover - defensive
        raise RuntimeError(f"Could not load a tokenizer for {model_name}")

    onnx_path = hf_hub_download(model_name, "onnx/model.onnx")
    session = InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    return tokenizer, session


def get_backend():
    """Return (tokenizer, session), loading once per process on first use."""
    global _tokenizer, _session
    if _tokenizer is None or _session is None:
        with _load_lock:
            if _tokenizer is None or _session is None:
                _tokenizer, _session = _build()
                logger.info(
                    "Loaded local embedding model %s (%d-dim)",
                    settings.EMBED_MODEL,
                    settings.EMBEDDING_DIM,
                )
    return _tokenizer, _session


def _mean_pool(last_hidden: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """CLS-free mean pooling with attention-mask weighting, then L2 normalise."""
    expanded = mask[..., None].astype(np.float32)
    summed = (last_hidden * expanded).sum(axis=1)
    counts = np.clip(expanded.sum(axis=1), 1e-9, None)
    pooled = summed / counts
    norms = np.linalg.norm(pooled, axis=1, keepdims=True)
    return pooled / np.clip(norms, 1e-9, None)


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Embed a batch. Returns (len(texts), EMBEDDING_DIM) float32, L2-normalised.

    L2-normalising here means the caller can use a plain inner product against
    a cosine HNSW index, which is what `<=>` does under the hood.
    """
    if not texts:
        return np.zeros((0, settings.EMBEDDING_DIM), dtype=np.float32)

    tokenizer, session = get_backend()

    # bge retrieval models expect this instruction on the query side only.
    prepared = [
        f"Represent this sentence for searching relevant passages: {t}" for t in texts
    ]

    encodings = [tokenizer.encode(t).ids[:MAX_SEQUENCE_TOKENS] for t in prepared]
    width = max(1, max(len(e) for e in encodings))
    input_ids = np.zeros((len(encodings), width), dtype=np.int64)
    attention_mask = np.zeros((len(encodings), width), dtype=np.int64)
    for row, ids in enumerate(encodings):
        if ids:
            input_ids[row, : len(ids)] = ids
            attention_mask[row, : len(ids)] = 1

    last_hidden = session.run(
        None,
        {
            "input_ids": input_ids,
            "token_type_ids": np.zeros_like(input_ids),
            "attention_mask": attention_mask,
        },
    )[0]

    vectors = _mean_pool(last_hidden, attention_mask).astype(np.float32)
    assert_dimensions(vectors)
    return vectors


def embed_query(text: str) -> np.ndarray:
    return embed_texts([text])[0]


def assert_dimensions(vectors: np.ndarray) -> None:
    """
    Fail loudly on a dimension mismatch.

    pgvector silently refuses to store a vector whose length differs from the
    column, so a wrong-dimension embedding surfaces much later as an insert
    error against a table nobody remembers creating. Catching it here turns a
    confusing runtime failure into an immediate one. See risks.md.
    """
    if vectors.ndim != 2 or vectors.shape[1] != settings.EMBEDDING_DIM:
        raise ValueError(
            f"Expected {settings.EMBEDDING_DIM}-dim embeddings, got shape {vectors.shape}. "
            f"Model {settings.EMBED_MODEL} does not match EMBEDDING_DIM; "
            "re-embedding is required if this changed."
        )
