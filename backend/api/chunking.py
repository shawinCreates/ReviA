"""
Page-bounded chunking.

A chunk is a slice of exactly one page, capped at CHUNK_TARGET_TOKENS with
CHUNK_OVERLAP_TOKENS of overlap. Never spans a page, which is what makes a
citation exact by construction rather than by bookkeeping: resolving `[3]` to a
page number cannot be ambiguous if no chunk crosses a page boundary.

Splitting is paragraph first, then sentence. Never mid-sentence, because a chunk
that starts in the middle of a sentence retrieves badly and reads nonsensically
when a user clicks the citation.

Token counting uses the embedding model's own tokenizer rather than a character
heuristic, so `token_count` means what the retriever will actually see. The
bge tokenizer is pure Rust and costs ~35MB, and it is already loaded for
embedding, so the alternative (tiktoken) would be both less accurate and a
second vocabulary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.conf import settings

CHUNK_TARGET_TOKENS = 800
CHUNK_OVERLAP_TOKENS = 100

# Sentence end followed by whitespace and something that starts a new sentence.
# Deliberately conservative: a false negative costs a slightly long chunk, a
# false positive splits mid-clause.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[A-Z0-9\"'(\[])")


@dataclass
class ChunkDraft:
    ordinal: int
    text: str
    token_count: int


_tokenizer = None


def _count_tokens(text: str) -> int:
    """
    Count tokens with the embedding tokenizer.

    Falls back to a character ratio if the model is not loadable, because
    chunking must not become impossible just because an optional local model
    is missing. The fallback is approximate and says so.
    """
    global _tokenizer
    if _tokenizer is None:
        try:
            from tokenizers import Tokenizer

            _tokenizer = Tokenizer.from_pretrained(settings.EMBED_MODEL)
        except Exception:  # noqa: BLE001
            _tokenizer = False  # type: ignore[assignment]

    if _tokenizer is False:
        # ~4 characters per token is the usual English rule of thumb.
        return max(1, len(text) // 4)

    return len(_tokenizer.encode(text).ids)


def _split_sentences(paragraph: str) -> list[str]:
    parts = _SENTENCE_BOUNDARY.split(paragraph)
    return [p for p in (s.strip() for s in parts) if p]


def chunk_page(text: str, start_ordinal: int = 0) -> list[ChunkDraft]:
    """
    Split one page's text into chunks. Returns chunks in reading order.

    A single page longer than the target is split across multiple chunks; a page
    shorter than the target becomes exactly one chunk regardless, because
    merging across pages would break the page-boundary guarantee.
    """
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if current:
            chunks.append("\n\n".join(current))
            current = []
            current_tokens = 0

    for paragraph in paragraphs:
        paragraph_tokens = _count_tokens(paragraph)

        # A paragraph that fits on its own and fills the chunk closes it.
        if paragraph_tokens >= CHUNK_TARGET_TOKENS:
            flush()
            chunks.extend(_chunk_long_paragraph(paragraph))
            continue

        if current_tokens + paragraph_tokens > CHUNK_TARGET_TOKENS:
            tail = _overlap_tail("\n\n".join(current))
            flush()
            if tail:
                current = [tail]
                current_tokens = _count_tokens(tail)

        current.append(paragraph)
        current_tokens += paragraph_tokens

    flush()
    return _apply_overlap(chunks, start_ordinal)


def _chunk_long_paragraph(paragraph: str) -> list[str]:
    """
    Split an oversized paragraph on sentence boundaries.

    If a single sentence is itself longer than the cap there is no safe split
    point, so it is emitted whole rather than cut mid-word. A pathological
    sentence therefore produces an oversized chunk, which is a lesser problem
    than a truncated citation.
    """
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sentence in _split_sentences(paragraph):
        sentence_tokens = _count_tokens(sentence)
        if current_tokens + sentence_tokens > CHUNK_TARGET_TOKENS and current:
            pieces.append(" ".join(current))
            tail = _overlap_tail(" ".join(current))
            current = [tail] if tail else []
            current_tokens = _count_tokens(tail) if tail else 0
        current.append(sentence)
        current_tokens += sentence_tokens

    if current:
        pieces.append(" ".join(current))
    return pieces


def _overlap_tail(text: str) -> str:
    """Last ~CHUNK_OVERLAP_TOKENS worth of text, snapped to a sentence start."""
    if not text:
        return ""
    sentences = _split_sentences(text)
    if not sentences:
        return ""
    tail: list[str] = []
    total = 0
    for sentence in reversed(sentences):
        tokens = _count_tokens(sentence)
        if total + tokens > CHUNK_OVERLAP_TOKENS and tail:
            break
        tail.insert(0, sentence)
        total += tokens
    return " ".join(tail)


def _apply_overlap(chunks: list[str], start_ordinal: int) -> list[ChunkDraft]:
    """
    Prepend the previous chunk's tail to each chunk after the first.

    The overlap is re-derived from the finished chunk list rather than carried
    during assembly, so a chunk that ended up shorter than expected still gets a
    correct tail.
    """
    drafts: list[ChunkDraft] = []
    for index, chunk in enumerate(chunks):
        if index > 0:
            tail = _overlap_tail(chunks[index - 1])
            if tail and tail not in chunk:
                chunk = f"{tail}\n\n{chunk}"
        drafts.append(
            ChunkDraft(
                ordinal=start_ordinal + index,
                text=chunk.strip(),
                token_count=_count_tokens(chunk),
            )
        )
    return drafts


def chunk_pages(pages: list[tuple[int, str]]) -> dict[int, list[ChunkDraft]]:
    """
    Chunk several pages, with ordinals restarting per page.

    `ordinal` is per-page rather than global on purpose: it is the sequence
    within a page, which is what a citation like "page 7, chunk 2" means to a
    reader. A global counter would be a meaningless number to display.
    """
    return {page_number: chunk_page(text) for page_number, text in pages}
