"""
Office document extraction: DOCX, PPTX, XLSX.

Direct libraries, not `unstructured`. Measured on the same fixtures,
`unstructured.partition.docx` peaks at 722MB where python-docx uses 33MB, and
the difference between those two numbers decides whether the app runs on a free
512MB instance at all. See fixtures/measure_parsers.py.

Page numbers are a property of the *container*, not the text:
  - PPTX: one slide is one page, so `page_number` is the slide number and a
    citation reads "slide 4", which is what a user can actually navigate to.
  - XLSX: one sheet is one page.
  - DOCX: Word paginates at render time, and that information is not in the
    file. An explicit page break is not reliably represented either. So DOCX is
    emitted as a single page and cited by its heading path instead. Inventing
    page numbers would produce citations pointing at a page Word never had.
    This is the product limitation, now measured rather than assumed.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Word's built-in heading styles. Anything else is body text, which matters:
# a document styled entirely with "Title" would otherwise become one enormous
# heading path.
_HEADING_STYLE = re.compile(r"^(?:heading|标题)\s*(\d+)$", re.IGNORECASE)
_TITLE_STYLES = {"title", "标题"}
_MAX_HEADING_CHARS = 120


@dataclass
class OfficePage:
    number: int
    text: str
    char_len: int
    heading_path: str | None = None


@dataclass
class OfficeDocument:
    pages: list[OfficePage] = field(default_factory=list)
    synthetic_pages: bool = False
    source_page_count: int | None = None


def parse_docx(path) -> OfficeDocument:
    """
    DOCX -> one page, carrying the document's heading outline.

    The whole document is one page, so `heading_path` is the full outline rather
    than only the final section. With one page there is no later page to carry
    the earlier headings, and a citation into a single-page "document" should be
    able to say where in the structure it came from.

    Headings come from Word's own `Heading N` styles, which is a far stronger
    signal than inferring structure from text, and means a document with no
    heading styles correctly reports no outline at all.
    """
    import docx

    document = docx.Document(str(path))
    outline: list[str] = []
    body: list[str] = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        if _heading_level(paragraph.style.name if paragraph.style else "", text) is not None:
            # Consecutive repeats of the same heading add nothing to an outline.
            if not outline or outline[-1] != text:
                outline.append(text)
            continue
        body.append(text)

    _append_tables(document, body)

    text = "\n\n".join(body).strip()
    heading = " > ".join(outline) if outline else None
    if not text:
        return OfficeDocument(synthetic_pages=True, source_page_count=1)

    return OfficeDocument(
        pages=[OfficePage(number=1, text=text, char_len=len(text), heading_path=heading)],
        synthetic_pages=True,
        source_page_count=1,
    )


def _heading_level(style: str, text: str) -> int | None:
    """Heading depth for a paragraph, or None if it is body text."""
    if len(text) > _MAX_HEADING_CHARS:
        return None
    if style.strip().lower() in _TITLE_STYLES:
        return 0
    match = _HEADING_STYLE.match(style.strip())
    if match:
        return int(match.group(1))
    return None


def _append_tables(document, body: list[str]) -> None:
    """
    Flatten tables to text.

    Table cells are real content in a paper's results table, and dropping them
    loses exactly the numbers a user might ask about. Cells are joined with a
    tab so a row stays on one line and remains searchable as a unit.
    """
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                body.append("\t".join(cells))


def parse_pptx(path) -> OfficeDocument:
    """PPTX -> one page per slide, which is a real, navigable page number."""
    from pptx import Presentation

    presentation = Presentation(str(path))
    document = OfficeDocument(source_page_count=len(presentation.slides))

    for number, slide in enumerate(presentation.slides, start=1):
        parts: list[str] = []
        title = None

        # The title placeholder, when present, leads: it is what the slide is
        # about and it reads first in the outline too.
        if slide.shapes.title is not None and slide.shapes.title.text.strip():
            title = slide.shapes.title.text.strip()
            parts.append(title)

        for shape in slide.shapes:
            if shape == slide.shapes.title:
                continue
            if getattr(shape, "has_text_frame", False):
                text = shape.text_frame.text.strip()
                if text:
                    parts.append(text)
            elif getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells]
                    if any(cells):
                        parts.append("\t".join(cells))

        text = "\n\n".join(parts).strip()
        if text:
            document.pages.append(
                OfficePage(
                    number=number, text=text, char_len=len(text), heading_path=title
                )
            )

    return document


def parse_xlsx(path) -> OfficeDocument:
    """XLSX -> one page per sheet, named so a citation can name the sheet."""
    import openpyxl

    workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    document = OfficeDocument(source_page_count=len(workbook.sheetnames))

    for number, name in enumerate(workbook.sheetnames, start=1):
        sheet = workbook[name]
        rows: list[str] = []
        for row in sheet.iter_rows(values_only=True):
            cells = ["" if c is None else str(c).strip() for c in row]
            if any(cells):
                rows.append("\t".join(cells))
        text = "\n".join(rows)
        if text.strip():
            document.pages.append(
                OfficePage(number=number, text=text, char_len=len(text), heading_path=name)
            )

    workbook.close()
    return document
