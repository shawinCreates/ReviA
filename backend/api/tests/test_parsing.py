"""
Parsing tests.

These lock in the page-number behaviour that was measured against real files on
2026-09-29, because page numbers are the phase 1 gate and a regression here is
silent: the app keeps working and every citation becomes subtly wrong.

Every PDF fixture writes a `PAGEMARKER-<FIXTURE>-<N>` string on page N, so the
expected page for a marker is knowable without trusting the parser.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from api.parsing import parse_document

FIXTURES = pathlib.Path(__file__).resolve().parents[2] / "fixtures"
MARKER = re.compile(r"PAGEMARKER-([A-Z]+)-(\d+)")


def fixture(name: str) -> pathlib.Path:
    path = FIXTURES / name
    if not path.exists():  # pragma: no cover - fixtures are committed
        pytest.skip(f"fixture {name} missing; run make_fixtures.py")
    return path


@pytest.fixture(scope="module")
def parsed():
    """Parse every fixture once. unstructured is slow and this is the bulk of the cost."""
    out = {}
    for name in [
        "single_column.pdf",
        "two_column.pdf",
        "rotated_figure.pdf",
        "heading.pdf",
        "deck.pptx",
        "headings.docx",
        "notes.md",
        "plain.txt",
    ]:
        out[name] = parse_document(fixture(name))
    return out


class TestPageNumbersAreCorrect:
    def test_markers_land_on_the_page_they_name(self, parsed):
        """
        The core gate. If this fails, every downstream citation is wrong.
        """
        for name, doc in parsed.items():
            if not name.endswith(".pdf"):
                continue
            seen: dict[int, set[int]] = {}
            for page in doc.pages:
                for _, num in MARKER.findall(page.text):
                    seen.setdefault(int(num), set()).add(page.page_number)
            assert seen, f"{name} produced no page markers at all"
            for expected, actual in seen.items():
                assert actual == {expected}, (
                    f"{name}: marker {expected} was attributed to {sorted(actual)}"
                )

    def test_pdf_pages_are_contiguous_from_one(self, parsed):
        for name in ["single_column.pdf", "two_column.pdf", "rotated_figure.pdf"]:
            numbers = [p.page_number for p in parsed[name].pages]
            assert numbers == list(range(1, len(numbers) + 1)), (
                f"{name}: page numbers not contiguous from 1: {numbers}"
            )

    def test_two_column_keeps_both_columns_on_their_own_page(self, parsed):
        """A naive reader concatenates columns; the wrong page must not absorb them."""
        for page in parsed["two_column.pdf"].pages:
            left = page.text.count("left col p")
            right = page.text.count("right col p")
            assert left == 12, f"page {page.page_number} lost left column: {left}"
            assert right == 12, f"page {page.page_number} lost right column: {right}"
            for other in range(1, 4):
                if other == page.page_number:
                    continue
                assert f"col p{other} " not in page.text, (
                    f"page {page.page_number} absorbed text from page {other}"
                )

    def test_slide_numbers_are_cited_as_pages(self, parsed):
        """PPTX does carry page numbers, and they are the slide numbers."""
        numbers = [p.page_number for p in parsed["deck.pptx"].pages]
        assert numbers == [1, 2, 3, 4]
        for page in parsed["deck.pptx"].pages:
            assert f"Slide {page.page_number} Title" in page.text


class TestFormatsWithoutPageMetadata:
    def test_docx_gets_one_synthetic_page(self, parsed):
        doc = parsed["headings.docx"]
        assert doc.synthetic_pages is True
        assert [p.page_number for p in doc.pages] == [1]

    def test_docx_cites_by_heading_path(self, parsed):
        """
        The DOCX page break is dropped by the parser, so heading path is the
        only citation precision available. It must be present.
        """
        heading = parsed["headings.docx"].pages[0].heading_path
        assert heading is not None
        assert "Top Level Heading" in heading
        assert "Second Level Heading" in heading

    def test_docx_loses_no_text(self, parsed):
        text = parsed["headings.docx"].pages[0].text
        for expected in [
            "Introductory paragraph",
            "Body text under the second level heading",
            "This paragraph is after an explicit page break",
        ]:
            assert expected in text

    def test_plain_text_is_not_all_headings(self, parsed):
        """
        Regression guard. unstructured tags every line of a .txt as Title.
        Believing that produced an empty document: all text went into the
        heading stack and nothing was left as body.
        """
        doc = parsed["plain.txt"]
        assert len(doc.pages) == 1
        page = doc.pages[0]
        assert page.char_len > 1000
        assert "plain text line 1" in page.text
        assert "plain text line 60" in page.text
        assert page.heading_path is None


class TestShape:
    def test_no_document_is_silently_empty(self, parsed):
        for name, doc in parsed.items():
            assert doc.pages, f"{name} parsed to zero pages"
            for page in doc.pages:
                assert page.text.strip(), f"{name} page {page.page_number} is empty"
                assert page.char_len == len(page.text)

    def test_pages_are_ascending(self, parsed):
        for name, doc in parsed.items():
            numbers = [p.page_number for p in doc.pages]
            assert numbers == sorted(numbers), f"{name}: pages out of order {numbers}"
