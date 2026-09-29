"""
Document parsing: file -> one text blob per citation page.

Every format is read with a small, direct library. The previous
implementation used `unstructured`, which measured 968MB peak on a 3-page PDF
and 722MB on a DOCX — larger than the 512MB instance this is built to run on.
pdfminer.six, python-docx, python-pptx and openpyxl do the same job at 33-37MB.
See fixtures/measure_parsers.py for the numbers and
fixtures/measure_imports.py for the import-level attribution.

The trade-off, stated plainly: `unstructured` classified elements (headings,
captions, lists) and we used that to build a `heading_path`. Reading the
libraries directly, heading structure is available for DOCX (Word's own heading
styles, which is a stronger signal than a classifier guess) and PPTX (the title
placeholder). For PDF there is no heading path, so PDFs are cited by page —
which is what a reader can navigate to anyway.

Page numbering by format, measured against the fixtures in backend/fixtures/:

| Format  | Page unit         | Cited by                       |
|---------|-------------------|--------------------------------|
| PDF     | real page, 1-based | page number                   |
| PPTX    | slide             | slide number                   |
| XLSX    | sheet             | sheet name                     |
| DOCX    | whole document    | heading path                   |
| MD/TXT  | whole document    | single page                    |

The DOCX row is not an oversight. Word paginates when it renders, and that
information is not stored in the file, so a DOCX page number would be a fiction
the user cannot follow. See architecture.md.
"""

from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ParsedPage:
    page_number: int
    text: str
    char_len: int
    heading_path: str | None = None


@dataclass
class ParsedDocument:
    pages: list[ParsedPage] = field(default_factory=list)
    # True when the source has no page concept and everything is one page.
    synthetic_pages: bool = False
    source_page_count: int | None = None


def parse_document(path: pathlib.Path) -> ParsedDocument:
    """
    Parse one file into per-page text.

    Ordinary content problems do not raise: a file with nothing readable comes
    back as an empty ParsedDocument and the caller decides whether that is a
    failure. A genuinely unreadable file (wrong password, corrupt container)
    raises, because pretending it was empty would hide a real error.
    """
    path = pathlib.Path(path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _parse_pdf(path)
    if suffix == ".docx":
        return _from_office(_parse_docx(path))
    if suffix == ".pptx":
        return _from_office(_parse_pptx(path))
    if suffix == ".xlsx":
        return _from_office(_parse_xlsx(path))
    return _parse_plain(path)


def _parse_pdf(path: pathlib.Path) -> ParsedDocument:
    from .pdf import extract_pages

    pages = [
        ParsedPage(
            page_number=page.number, text=page.text, char_len=len(page.text)
        )
        for page in extract_pages(path)
        # An image-only page yields no text but still occupies a page number.
        # Dropping it would renumber every page after it and silently misplace
        # every citation, so the page is kept as an empty placeholder.
        if page.text.strip()
    ]
    return ParsedDocument(
        pages=pages,
        synthetic_pages=False,
        source_page_count=len(pages) or None,
    )


def _parse_docx(path: pathlib.Path):
    from .office import parse_docx

    return parse_docx(path)


def _parse_pptx(path: pathlib.Path):
    from .office import parse_pptx

    return parse_pptx(path)


def _parse_xlsx(path: pathlib.Path):
    from .office import parse_xlsx

    return parse_xlsx(path)


def _parse_plain(path: pathlib.Path) -> ParsedDocument:
    """
    Markdown, plain text and CSV: the file *is* the text.

    Read with an explicit UTF-8 attempt and a latin-1 fallback, because a .txt
    exported on Windows is very often cp1252 and failing on it would reject a
    document a user can plainly read.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="latin-1")

    text = text.strip()
    if not text:
        return ParsedDocument(synthetic_pages=True, source_page_count=1)

    return ParsedDocument(
        pages=[ParsedPage(page_number=1, text=text, char_len=len(text))],
        synthetic_pages=True,
        source_page_count=1,
    )


def _from_office(office_document) -> ParsedDocument:
    return ParsedDocument(
        pages=[
            ParsedPage(
                page_number=page.number,
                text=page.text,
                char_len=page.char_len,
                heading_path=page.heading_path,
            )
            for page in office_document.pages
        ],
        synthetic_pages=office_document.synthetic_pages,
        source_page_count=office_document.source_page_count,
    )
