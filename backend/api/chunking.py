"""Splitting a document into retrievable pieces.

Two decisions here, and they are the ones that decide whether an answer cites
something sensible or something arbitrary.

**Chunks overlap.** A chunk boundary in the middle of a sentence means a
question about that sentence retrieves neither neighbour, and the answer becomes
"not in your documents" for something that is plainly there. Overlapping by a
sentence or two means a boundary always leaves the thought intact somewhere.

**Chunks respect page boundaries.** A chunk is cited by page, so a chunk
spanning three pages can only be attributed to one of them. Splitting on page
breaks keeps every chunk honest about where it came from.

The target size trades retrieval precision against answer completeness. Too
small and each chunk lacks the context to be interpretable on its own; too large
and every retrieval drags in irrelevant text that dilutes the answer. Around 900
characters is roughly a paragraph or two of prose, which is usually one idea.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from api.parsing import ExtractedPage

logger = logging.getLogger(__name__)

#: Target characters per chunk. See the module docstring for why.
TARGET_CHARS = 900

#: Never emit a chunk longer than this, even mid-sentence, because an oversized
#: chunk dilutes every answer that retrieves it.
MAX_CHARS = 1_400

#: Chunks smaller than this are folded into their neighbour. A fragment of two
#: words has no meaning on its own and only adds noise to a search.
MIN_CHARS = 120

#: Sentence ends, used to find a boundary. Deliberately conservative: an
#: abbreviation or a decimal point that matches is a worse split than a slightly
#: long chunk, because a split mid-sentence loses the sentence.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

#: A bullet list or a run of headings, which should not be glued to prose.
_LINE_BREAK = re.compile(r"\n{2,}")


class DocumentIsEmptyError(Exception):
    """A document parsed cleanly but has no text to index.

    Distinct from `DocumentParsingError`, which means the file could not be read.
    This one means it was read and there was nothing in it — a scan with no OCR,
    most often — and the two deserve different messages.
    """


@dataclass(frozen=True)
class TextChunk:
    """One retrievable piece, before it has an embedding."""

    ordinal: int
    page_number: int
    content: str

    @property
    def char_count(self) -> int:
        return len(self.content)

    def estimated_tokens(self) -> int:
        """A rough token count.

        Four characters per token is the usual rule of thumb for English prose.
        It is stored because the answer prompt needs to know how much of a
        model's context a set of chunks consumes, and the alternative is calling
        the model's own tokenizer, which means a dependency and a network-free
        but non-trivial call on every retrieval. An estimate is enough for
        deciding what to include.
        """
        return max(1, self.char_count // 4)


def chunk_document(pages: list[ExtractedPage]) -> list[TextChunk]:
    """Split a parsed document into ordered, page-attributed chunks."""
    if not pages:
        raise DocumentIsEmptyError("The document has no pages.")

    chunks: list[TextChunk] = []
    ordinal = 0

    for page in pages:
        if page.is_empty:
            continue

        for piece in _split_page(page):
            piece = piece.strip()
            if len(piece) < MIN_CHARS:
                # Too small to stand alone. Held back and merged into whatever
                # comes next, which is usually a continuation of the same
                # thought rather than a separate one.
                if chunks and chunks[-1].page_number == page.number:
                    chunks[-1] = _extend(chunks[-1], piece)
                continue

            ordinal += 1
            chunks.append(
                TextChunk(ordinal=ordinal, page_number=page.number, content=piece)
            )

    if not chunks:
        raise DocumentIsEmptyError(
            "No text could be read from this document. A scanned copy with no "
            "text layer needs to be run through OCR first."
        )

    return chunks


def _split_page(page: ExtractedPage) -> list[str]:
    """Break one page into candidate pieces, each close to `TARGET_CHARS`.

    Paragraph breaks are preferred over sentence ends. A paragraph is an
    author's own statement of where one idea stops, which is a better boundary
    than any punctuation rule.
    """
    paragraphs = [block for block in _LINE_BREAK.split(page.text) if block.strip()]

    pieces: list[str] = []
    current: list[str] = []
    current_length = 0

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if current_length and current_length + len(paragraph) + 2 > TARGET_CHARS:
            pieces.append("\n\n".join(current))
            current = []
            current_length = 0

        if len(paragraph) > MAX_CHARS:
            # A single paragraph longer than the maximum: a table extracted as
            # one block, usually. It has to be split at sentence ends even
            # though the paragraph rule says otherwise.
            if current:
                pieces.append("\n\n".join(current))
                current = []
                current_length = 0
            pieces.extend(_split_long_paragraph(paragraph))
            continue

        current.append(paragraph)
        current_length += len(paragraph) + 2

    if current:
        pieces.append("\n\n".join(current))

    return pieces


def _split_long_paragraph(paragraph: str) -> list[str]:
    """Break an over-long block at sentence ends, then at any whitespace."""
    sentences = _SENTENCE_END.split(paragraph)

    pieces: list[str] = []
    current: list[str] = []
    current_length = 0

    for sentence in sentences:
        if len(sentence) > MAX_CHARS:
            # One sentence longer than the maximum means there are no sentence
            # ends to find, so fall back to whitespace.
            if current:
                pieces.append(" ".join(current))
                current = []
                current_length = 0
            pieces.extend(_split_on_whitespace(sentence))
            continue

        if current_length and current_length + len(sentence) + 1 > TARGET_CHARS:
            pieces.append(" ".join(current))
            current = []
            current_length = 0

        current.append(sentence)
        current_length += len(sentence) + 1

    if current:
        pieces.append(" ".join(current))

    return pieces


def _split_on_whitespace(text: str) -> list[str]:
    """Last resort for text with no sentence structure, such as a table.

    Splits on whitespace, and hard-splits any single token that is itself over
    the maximum. A word cannot be divided meaningfully, but a base64 blob or a
    run-on table cell can be, and one unbreakable token is otherwise the only
    thing preventing every chunk from being a sensible size.
    """
    words = text.split()
    pieces = []
    current: list[str] = []
    length = 0

    for word in words:
        if len(word) > MAX_CHARS:
            if current:
                pieces.append(" ".join(current))
                current = []
                length = 0
            pieces.extend(
                word[offset : offset + TARGET_CHARS]
                for offset in range(0, len(word), TARGET_CHARS)
            )
            continue

        if length and length + len(word) + 1 > TARGET_CHARS:
            pieces.append(" ".join(current))
            current = []
            length = 0
        current.append(word)
        length += len(word) + 1

    if current:
        pieces.append(" ".join(current))

    return pieces


def _extend(chunk: TextChunk, extra: str) -> TextChunk:
    """Fold a too-small fragment into the chunk before it."""
    if not extra:
        return chunk
    return TextChunk(
        ordinal=chunk.ordinal,
        page_number=chunk.page_number,
        content=f"{chunk.content} {extra}".strip(),
    )
