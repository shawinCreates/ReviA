"""Pulling text out of an uploaded file, one reader per format.

Each reader returns `ExtractedPage` objects rather than a single string, because
the page number is what an answer has to cite. A document flattened to one blob
can still be quoted, but not pointed at, and pointing at the source is the
entire premise of the product.

The readers are chosen by extension. That is safe only because
`api.uploads` has already confirmed the file's magic bytes match the extension
it claims, so the extension is not attacker-controlled in a way that matters
here.

Nothing in this module touches the database or the network. Parsing a
malformed file is expected to be ordinary rather than exceptional — people
upload truncated downloads and scanned documents with no text layer at all —
so each reader turns a parse failure into a `DocumentParsingError` carrying a
message a user can act on, rather than a stack trace.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)

#: Below this, a page is treated as empty. Real pages carry a few hundred
#: characters; a handful is a header or a page number left behind by the layout.
_MIN_CHARS_PER_PAGE = 10


class DocumentParsingError(Exception):
    """The file could not be turned into text.

    `reason` is shown to the user, so it says what is wrong with the file rather
    than what went wrong internally.
    """

    def __init__(self, reason: str, *, code: str = "parse_failed"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


@dataclass(frozen=True)
class ExtractedPage:
    """One page of a document.

    `number` is 1-based because that is how pages are referred to in a citation
    and in a document viewer. A 0-based number would need converting at every
    place it is shown, which is exactly the sort of off-by-one that ships.
    """

    number: int
    text: str

    @property
    def is_empty(self) -> bool:
        return len(self.text.strip()) < _MIN_CHARS_PER_PAGE


def extract_pages(filename: str, data: bytes) -> list[ExtractedPage]:
    """Turn a file into pages of text, or raise `DocumentParsingError`."""
    suffix = PurePosixPath(filename).suffix.lower()

    reader = _READERS.get(suffix)
    if reader is None:
        # Unreachable through the upload endpoint, which filters by allowlist.
        # Reached by a document re-read after the allowlist changed.
        raise DocumentParsingError(
            f"No reader is available for {suffix or 'this file type'}.",
            code="unsupported_format",
        )

    if not data:
        raise DocumentParsingError("That file is empty.", code="empty_file")

    return reader(data)


# --- readers ---------------------------------------------------------------------


def _read_pdf(data: bytes) -> list[ExtractedPage]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        # A PDF can declare pages it does not contain, and an encrypted one asks
        # for a password nobody has. Both are the file's problem, not a bug.
        if reader.is_encrypted:
            raise DocumentParsingError(
                "That PDF is password-protected, so its text cannot be read.",
                code="encrypted",
            )

        pages = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                # One unreadable page should not lose the whole document. A
                # scanned page with no text layer raises here, and the rest of
                # the file is still worth having.
                logger.info("Page %d of a PDF did not yield text: %s", index, exc)
                text = ""
            pages.append(ExtractedPage(number=index, text=_normalise(text)))

        if not pages:
            raise DocumentParsingError(
                "That PDF has no pages to read.", code="no_pages"
            )

        return pages
    except DocumentParsingError:
        raise
    except PdfReadError as exc:
        raise DocumentParsingError(
            "That PDF could not be opened; it may be damaged or incomplete.",
            code="corrupt",
        ) from exc
    except Exception as exc:
        logger.exception("PDF extraction failed")
        raise DocumentParsingError(
            f"That PDF could not be read: {type(exc).__name__}", code="parse_failed"
        ) from exc


def _read_docx(data: bytes) -> list[ExtractedPage]:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise DocumentParsingError(
            "That Word file could not be opened; it may be damaged.",
            code="corrupt",
        ) from exc

    # Word has no pages, only a flow of paragraphs and tables. It is presented as
    # a single page so the citation reads "page 1" and stays consistent with the
    # other formats. A page number that is always 1 is honest; inventing page
    # boundaries from paragraph breaks would be a guess dressed as a fact.
    blocks = [paragraph.text for paragraph in document.paragraphs]

    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                blocks.append(" | ".join(cells))

    return [ExtractedPage(number=1, text=_normalise("\n".join(blocks)))]


def _read_pptx(data: bytes) -> list[ExtractedPage]:
    import pptx

    try:
        presentation = pptx.Presentation(io.BytesIO(data))
    except Exception as exc:
        raise DocumentParsingError(
            "That PowerPoint file could not be opened; it may be damaged.",
            code="corrupt",
        ) from exc

    pages = []
    for index, slide in enumerate(presentation.slides, start=1):
        blocks = []

        for shape in slide.shapes:
            # A slide holds more than text: images, charts, connectors. Only
            # shapes that carry a text frame can contribute, and asking one for
            # its text is an error, so this is filtered rather than caught.
            if not getattr(shape, "has_text_frame", False):
                continue
            for paragraph in shape.text_frame.paragraphs:
                if paragraph.text.strip():
                    blocks.append(paragraph.text)

        if getattr(slide, "has_notes_slide", False):
            notes = slide.notes_slide.notes_text_frame.text
            if notes and notes.strip():
                # Speaker notes are often the most valuable text in a deck, and
                # a slide's own text is often just its title.
                blocks.append(notes)

        pages.append(ExtractedPage(number=index, text=_normalise("\n".join(blocks))))

    if not pages:
        raise DocumentParsingError("That presentation has no slides.", code="no_pages")

    return pages


_READERS = {
    ".pdf": _read_pdf,
    ".docx": _read_docx,
    ".pptx": _read_pptx,
}


def _normalise(text: str) -> str:
    """Tidy extracted text without changing what it says.

    Three things. NUL bytes are removed, because a PDF whose font carries a
    broken encoding map can yield them and Postgres refuses to store a NUL in a
    `text` column — one stray byte in one page otherwise fails the whole document
    with an error that says nothing about PDF extraction. Runs of spaces and tabs
    become single spaces, because extraction leaves one space per column gap and
    the raw text is close to unreadable. And blank lines are collapsed to a
    single one, so paragraph structure survives without a wall of whitespace from
    layout.

    Newlines are kept: a list of extracted lines is not the same as prose, and
    the chunker works better with the line structure intact.
    """
    # Before the line split, because `str.split()` treats whitespace specially
    # and a NUL is not whitespace, so it would ride through untouched.
    text = text.replace("\x00", "")

    lines = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        # `split()` rather than a regex, so a line that is only spaces becomes
        # empty and can be collapsed with the others.
        cleaned = " ".join(line.split())
        lines.append(cleaned)

    paragraphs: list[str] = []
    previous_blank = True
    for line in lines:
        if line:
            paragraphs.append(line)
            previous_blank = False
        elif not previous_blank:
            paragraphs.append("")
            previous_blank = True

    return "\n".join(paragraphs).strip()


def page_count(pages: list[ExtractedPage]) -> int:
    """How many pages a document has.

    Scanned PDFs often produce pages with no text layer at all, so counting only
    the pages that yielded text would report a 40-page scan as empty. The
    structural count is what a user means by "page count".
    """
    return len(pages)


def usable_text(pages: list[ExtractedPage]) -> str:
    """The document's text, with empty pages dropped.

    Used for the "does this document have anything in it" check. A PDF that
    opens cleanly but is a photograph of a page has no text to search, and
    saying so is more useful than an answer that silently cites nothing.
    """
    return "\n\n".join(page.text for page in pages if not page.is_empty)
