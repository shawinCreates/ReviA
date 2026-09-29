"""
Office and plain-text extraction tests.

The behaviour that matters is what a citation can point at:
  - PPTX: the slide number must equal the slide's real position
  - XLSX: each sheet is its own page, named
  - DOCX: one synthetic page carrying the heading outline
  - MD/TXT: readable even when the bytes are not UTF-8
"""

from __future__ import annotations

import pathlib

import pytest

from api.parsing import parse_document

FIXTURES = pathlib.Path(__file__).resolve().parents[2] / "fixtures"


def fixture(name: str) -> pathlib.Path:
    path = FIXTURES / name
    if not path.exists():  # pragma: no cover
        pytest.skip(f"fixture {name} missing; run make_fixtures.py")
    return path


class TestPptx:
    def test_one_page_per_slide_in_order(self):
        document = parse_document(fixture("deck.pptx"))
        assert [p.page_number for p in document.pages] == [1, 2, 3, 4]

    def test_slide_content_does_not_bleed_across_slides(self):
        """The failure this guards against is slide 3's page containing slide
        2's body, which would cite the wrong slide."""
        document = parse_document(fixture("deck.pptx"))
        for page in document.pages:
            assert f"Body content for slide {page.page_number}" in page.text
            for other in range(1, 5):
                if other != page.page_number:
                    assert f"Body content for slide {other}" not in page.text

    def test_slide_title_becomes_the_heading(self):
        document = parse_document(fixture("deck.pptx"))
        # A slide title is a real, navigable locator, so it is worth keeping.
        assert document.pages[0].heading_path

    def test_source_page_count_is_the_slide_count(self):
        assert parse_document(fixture("deck.pptx")).source_page_count == 4


class TestDocx:
    def test_is_one_synthetic_page(self):
        document = parse_document(fixture("headings.docx"))
        assert len(document.pages) == 1
        assert document.synthetic_pages is True

    def test_heading_outline_is_preserved(self):
        heading = parse_document(fixture("headings.docx")).pages[0].heading_path
        assert heading
        assert "Top Level Heading" in heading
        assert "Second Level Heading" in heading
        assert "Chapter Two" in heading

    def test_body_text_is_not_treated_as_headings(self):
        heading = parse_document(fixture("headings.docx")).pages[0].heading_path
        assert "Introductory paragraph" not in heading

    def test_text_after_a_page_break_is_not_lost(self):
        """Word paginates at render time, so the break is not recoverable. The
        text after it still has to be there."""
        text = parse_document(fixture("headings.docx")).pages[0].text
        assert "after an explicit page break" in text

    def test_a_document_with_no_heading_styles_reports_no_outline(self, tmp_path):
        import docx

        document = docx.Document()
        document.add_paragraph("Just a plain paragraph.")
        document.add_paragraph("And another one.")
        path = tmp_path / "flat.docx"
        document.save(path)

        parsed = parse_document(path)
        assert parsed.pages[0].heading_path is None
        assert "plain paragraph" in parsed.pages[0].text


class TestXlsx:
    @pytest.fixture
    def workbook(self, tmp_path):
        import openpyxl

        book = openpyxl.Workbook()
        first = book.active
        first.title = "Measurements"
        first.append(["sample", "value"])
        first.append(["a", 1.5])
        second = book.create_sheet("Notes")
        second.append(["note"])
        second.append(["the control group was noisy"])
        book.save(tmp_path / "book.xlsx")
        return tmp_path / "book.xlsx"

    def test_each_sheet_is_its_own_page(self, workbook):
        document = parse_document(workbook)
        assert [p.page_number for p in document.pages] == [1, 2]

    def test_sheet_name_is_the_heading(self, workbook):
        document = parse_document(workbook)
        assert document.pages[0].heading_path == "Measurements"
        assert document.pages[1].heading_path == "Notes"

    def test_cell_values_are_searchable(self, workbook):
        document = parse_document(workbook)
        assert "1.5" in document.pages[0].text
        assert "control group" in document.pages[1].text


class TestPlainText:
    def test_markdown_is_read_verbatim(self):
        document = parse_document(fixture("notes.md"))
        assert len(document.pages) == 1
        assert document.synthetic_pages is True
        assert len(document.pages[0].text) > 100

    def test_plain_text_keeps_every_line(self):
        document = parse_document(fixture("plain.txt"))
        expected = len(
            [l for l in fixture("plain.txt").read_text().splitlines() if l.strip()]
        )
        actual = len([l for l in document.pages[0].text.splitlines() if l.strip()])
        assert actual == expected

    def test_non_utf8_bytes_do_not_reject_the_file(self, tmp_path):
        """A .txt exported on Windows is often cp1252. Failing on it would
        reject a document the user can plainly read."""
        path = tmp_path / "legacy.txt"
        path.write_bytes("Résumé naïve café".encode("latin-1"))
        document = parse_document(path)
        assert "caf" in document.pages[0].text

    def test_an_empty_file_yields_no_pages(self, tmp_path):
        path = tmp_path / "empty.txt"
        path.write_text("")
        assert parse_document(path).pages == []


class TestUnknownFormat:
    def test_an_unrecognised_extension_is_read_as_text(self, tmp_path):
        """Better to index the bytes than to refuse a file the user can open."""
        path = tmp_path / "notes.rst"
        path.write_text("Some reStructuredText content.")
        assert "reStructuredText" in parse_document(path).pages[0].text
