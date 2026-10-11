from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from api.parsing import ExtractedBlock, ExtractedPage

logger = logging.getLogger(__name__)

TARGET_CHARS = 900

MAX_CHARS = 1_400

MIN_CHARS = 120

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

HEADING_JOIN = " > "


class DocumentIsEmptyError(Exception):
    pass


@dataclass(frozen=True)
class TextChunk:
    ordinal: int
    page_number: int
    content: str
    heading_path: str = ""

    @property
    def char_count(self) -> int:
        return len(self.content)

    def estimated_tokens(self) -> int:
        return max(1, self.char_count // 4)


@dataclass
class _Section:
    path: str
    blocks: list[ExtractedBlock] = field(default_factory=list)

    @property
    def heading_lines(self) -> list[str]:
        if not self.path:
            return []
        return self.path.split(HEADING_JOIN)


def chunk_document(pages: list[ExtractedPage]) -> list[TextChunk]:
    if not pages:
        raise DocumentIsEmptyError("The document has no pages.")

    sections = _collect_sections(pages)
    chunks: list[TextChunk] = []

    for section in sections:
        prefix = "\n\n".join(section.heading_lines)

        for body, page in _split_body(section):
            content = f"{prefix}\n\n{body}" if prefix else body

            if (
                chunks
                and chunks[-1].heading_path == section.path
                and len(content) < MIN_CHARS
            ):
                previous = chunks[-1]
                chunks[-1] = TextChunk(
                    ordinal=previous.ordinal,
                    page_number=previous.page_number,
                    content=f"{previous.content} {content}".strip(),
                    heading_path=previous.heading_path,
                )
                continue

            chunks.append(
                TextChunk(
                    ordinal=len(chunks) + 1,
                    page_number=page,
                    content=content,
                    heading_path=section.path,
                )
            )

    if not chunks:
        raise DocumentIsEmptyError(
            "No text could be read from this document. A scanned copy with no "
            "text layer needs to be run through OCR first."
        )

    return chunks


def _collect_sections(pages: list[ExtractedPage]) -> list[_Section]:
    stack: list[str] = []
    sections: list[_Section] = []
    current = _Section("")

    for page in pages:
        for block in page.blocks:
            if block.level is None:
                current.blocks.append(block)
                continue

            sections.append(current)
            level = max(1, block.level)
            stack = [*stack[: level - 1], block.text]
            current = _Section(HEADING_JOIN.join(stack))

    sections.append(current)
    return sections


def _split_body(section: _Section) -> list[tuple[str, int]]:
    blocks = [block for block in section.blocks if block.text.strip()]

    pieces: list[tuple[str, int]] = []
    current: list[str] = []
    current_length = 0
    current_page = blocks[0].page_number if blocks else 1

    for block in blocks:
        paragraph = block.text.strip()

        if current_length and current_length + len(paragraph) + 2 > TARGET_CHARS:
            pieces.append(("\n\n".join(current), current_page))
            current = []
            current_length = 0

        if len(paragraph) > MAX_CHARS:
            if current:
                pieces.append(("\n\n".join(current), current_page))
                current = []
                current_length = 0
            pieces.extend(
                (piece, block.page_number) for piece in _split_long_paragraph(paragraph)
            )
            continue

        if not current:
            current_page = block.page_number
        current.append(paragraph)
        current_length += len(paragraph) + 2

    if current:
        pieces.append(("\n\n".join(current), current_page))

    return pieces


def _split_long_paragraph(paragraph: str) -> list[str]:
    sentences = _SENTENCE_END.split(paragraph)

    pieces: list[str] = []
    current: list[str] = []
    current_length = 0

    for sentence in sentences:
        if len(sentence) > MAX_CHARS:
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
