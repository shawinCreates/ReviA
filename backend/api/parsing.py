from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)

_MIN_CHARS_PER_PAGE = 10

_NOISE_CATEGORIES = frozenset({"Header", "Footer", "PageBreak"})

_HEADING_CATEGORY = "Title"


class DocumentParsingError(Exception):
    def __init__(self, reason: str, *, code: str = "parse_failed"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


@dataclass(frozen=True)
class ExtractedBlock:
    text: str
    level: int | None = None
    page_number: int = 1


@dataclass(frozen=True)
class ExtractedPage:
    number: int
    blocks: tuple[ExtractedBlock, ...] = ()

    @property
    def text(self) -> str:
        return "\n".join(block.text for block in self.blocks)

    @property
    def is_empty(self) -> bool:
        return len(self.text.strip()) < _MIN_CHARS_PER_PAGE


def extract_pages(filename: str, data: bytes) -> list[ExtractedPage]:
    suffix = PurePosixPath(filename).suffix.lower()

    reader = _READERS.get(suffix)
    if reader is None:
        raise DocumentParsingError(
            f"No reader is available for {suffix or 'this file type'}.",
            code="unsupported_format",
        )

    if not data:
        raise DocumentParsingError("That file is empty.", code="empty_file")

    return _group_into_pages(reader(data))


def _read_pdf(data: bytes) -> list[ExtractedBlock]:
    from django.conf import settings
    from unstructured.partition.pdf import partition_pdf

    strategy = getattr(settings, "PDF_PARTITION_STRATEGY", "hi_res")

    try:
        elements = _partition_pdf(partition_pdf, data, strategy)
    except Exception as exc:
        logger.info("PDF extraction with %r failed: %s", strategy, exc)
        raise DocumentParsingError(
            "That PDF could not be read; it may be damaged or password-protected.",
            code="corrupt",
        ) from exc

    return _elements_to_blocks(elements)


def _partition_pdf(partition_pdf, data: bytes, strategy: str) -> list:
    try:
        return partition_pdf(
            file=io.BytesIO(data), strategy=strategy, include_page_breaks=True
        )
    except Exception as exc:
        if strategy == "fast":
            raise
        logger.warning(
            "PDF partition with %r failed (%s); retrying with 'fast'", strategy, exc
        )
        return partition_pdf(
            file=io.BytesIO(data), strategy="fast", include_page_breaks=True
        )


def _read_docx(data: bytes) -> list[ExtractedBlock]:
    from unstructured.partition.docx import partition_docx

    try:
        elements = partition_docx(file=io.BytesIO(data))
    except Exception as exc:
        raise DocumentParsingError(
            "That Word file could not be opened; it may be damaged.",
            code="corrupt",
        ) from exc

    return _elements_to_blocks(elements)


def _read_pptx(data: bytes) -> list[ExtractedBlock]:
    from unstructured.partition.pptx import partition_pptx

    try:
        elements = partition_pptx(file=io.BytesIO(data), include_page_breaks=True)
    except Exception as exc:
        raise DocumentParsingError(
            "That PowerPoint file could not be opened; it may be damaged.",
            code="corrupt",
        ) from exc

    return _elements_to_blocks(elements)

_READERS = {
    ".pdf": _read_pdf,
    ".docx": _read_docx,
    ".pptx": _read_pptx,
}


def _elements_to_blocks(elements: list) -> list[ExtractedBlock]:
    blocks: list[ExtractedBlock] = []
    page = 1

    for element in elements:
        category = getattr(element, "category", None)

        if category == "PageBreak":
            page += 1
            continue
        if category in _NOISE_CATEGORIES:
            continue

        text = _normalise(getattr(element, "text", "") or "")
        if not text:
            continue
        if blocks and blocks[-1].text == text:
            continue

        level = _heading_level(element) if category == _HEADING_CATEGORY else None

        reported = getattr(element.metadata, "page_number", None)
        if isinstance(reported, int) and reported >= 1:
            page = reported

        blocks.append(ExtractedBlock(text=text, level=level, page_number=page))

    return blocks


def _heading_level(element) -> int:
    depth = getattr(element.metadata, "category_depth", None)
    if isinstance(depth, int) and depth >= 0:
        return depth + 1
    return 1


def _group_into_pages(blocks: list[ExtractedBlock]) -> list[ExtractedPage]:
    by_page: dict[int, list[ExtractedBlock]] = {}
    for block in blocks:
        by_page.setdefault(block.page_number, []).append(block)

    return [
        ExtractedPage(number=number, blocks=tuple(page_blocks))
        for number, page_blocks in sorted(by_page.items())
    ]


def _normalise(text: str) -> str:
    text = text.replace("\x00", "")

    lines = [
        " ".join(line.split())
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]

    kept: list[str] = []
    previous_blank = True
    for line in lines:
        if line:
            kept.append(line)
            previous_blank = False
        elif not previous_blank:
            kept.append("")
            previous_blank = True

    return "\n".join(kept).strip()


def page_count(pages: list[ExtractedPage]) -> int:
    return len(pages)


def usable_text(pages: list[ExtractedPage]) -> str:
    return "\n\n".join(page.text for page in pages if not page.is_empty)
