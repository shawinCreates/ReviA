"""
PDF extraction tests.

Two things are being protected here, and both were bugs during development:

1. Page numbers. A citation that points at the wrong page is worse than no
   citation, so every fixture writes a `PAGEMARKER-<FIXTURE>-<N>` string on
   page N and the test asserts the marker is on the page it names.

2. Column detection. pdfminer emits text in coordinate order, which on a
   two-column page interleaves the columns line by line and shreds sentences.
   The gutter detection has to fire on a two-column page and, just as
   importantly, NOT fire on a single-column one.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from api.pdf import MIN_GUTTER_POINTS, TextBox, extract_pages, split_columns

FIXTURES = pathlib.Path(__file__).resolve().parents[2] / "fixtures"
MARKER = re.compile(r"PAGEMARKER-([A-Z]+)-(\d+)")
PAGE_WIDTH = 612.0  # US Letter, which every fixture uses


def fixture(name: str) -> pathlib.Path:
    path = FIXTURES / name
    if not path.exists():  # pragma: no cover
        pytest.skip(f"fixture {name} missing; run make_fixtures.py")
    return path


def box(x0, x1, y0=700.0, y1=710.0, text="x") -> TextBox:
    return TextBox(x0=x0, x1=x1, y0=y0, y1=y1, text=text)


class TestPageNumbers:
    @pytest.mark.parametrize(
        "name", ["single_column.pdf", "two_column.pdf", "rotated_figure.pdf"]
    )
    def test_markers_land_on_the_page_they_name(self, name):
        pages = extract_pages(str(fixture(name)))
        for page in pages:
            for _, number in MARKER.findall(page.text):
                assert int(number) == page.number, (
                    f"{name}: marker for page {number} was found on page {page.number}"
                )

    def test_pages_are_numbered_from_one_without_gaps(self):
        pages = extract_pages(str(fixture("single_column.pdf")))
        assert [p.number for p in pages] == [1, 2, 3]

    def test_every_page_has_text(self):
        for page in extract_pages(str(fixture("single_column.pdf"))):
            assert page.text.strip(), f"page {page.number} came back empty"

    def test_a_large_document_still_numbers_correctly(self, tmp_path):
        from reportlab.lib.pagesizes import LETTER
        from reportlab.pdfgen import canvas

        path = tmp_path / "long.pdf"
        c = canvas.Canvas(str(path), pagesize=LETTER)
        for page in range(1, 41):
            c.drawString(72, 720, f"PAGEMARKER-LONG-{page}")
            c.drawString(72, 700, f"Body text for page {page} of the document.")
            c.showPage()
        c.save()

        pages = extract_pages(str(path))
        assert len(pages) == 40
        for page in pages:
            assert f"PAGEMARKER-LONG-{page.number}" in page.text


class TestColumnDetection:
    def test_two_column_layout_is_detected(self):
        pages = extract_pages(str(fixture("two_column.pdf")))
        assert all(p.column_count == 2 for p in pages)

    @pytest.mark.parametrize(
        "name", ["single_column.pdf", "heading.pdf", "rotated_figure.pdf"]
    )
    def test_single_column_layout_is_not_misdetected(self, name):
        """A false positive is its own bug: it would reorder a normal page."""
        for page in extract_pages(str(fixture(name))):
            assert page.column_count == 1, f"{name} page {page.number} split wrongly"

    def test_columns_are_read_left_before_right(self):
        pages = extract_pages(str(fixture("two_column.pdf")))
        lines = [l for l in pages[0].text.splitlines() if l.strip()]
        left = [i for i, l in enumerate(lines) if l.lower().startswith("left")]
        right = [i for i, l in enumerate(lines) if l.lower().startswith("right")]
        assert left and right
        assert max(left) < min(right), "columns are interleaved, not sequential"

    def test_a_full_width_title_is_kept_and_comes_first(self):
        """The title spans the gutter. Dropping it would lose the document's
        name, and filing it in the right column would put it mid-page."""
        pages = extract_pages(str(fixture("two_column.pdf")))
        first = pages[0].text.splitlines()[0]
        assert "TWO COLUMN" in first

    def test_no_text_is_lost_to_column_assignment(self):
        """An early version dropped five boxes per page by testing each box's
        *right* edge against the gutter. Every box must appear exactly once."""
        for page in extract_pages(str(fixture("two_column.pdf"))):
            assert "PAGEMARKER-TWOCOL" in page.text
            lines = [l for l in page.text.splitlines() if l.strip()]
            # 12 left lines + 12 right lines + title + page marker
            assert len(lines) == 26, f"page {page.number} lost boxes"
            assert sum("left col" in l for l in lines) == 12
            assert sum("right col" in l for l in lines) == 12


class TestSplitColumnsUnit:
    def test_a_gutter_in_the_middle_splits(self):
        boxes = [box(72, 140, y0=700 - i * 20) for i in range(5)]
        boxes += [box(330, 400, y0=700 - i * 20) for i in range(5)]
        assert len(split_columns(boxes, PAGE_WIDTH)) == 2

    def test_word_spacing_is_not_mistaken_for_a_gutter(self):
        """Boxes separated by an ordinary 5pt gap must stay one column."""
        boxes = [box(72, 140, y0=700 - i * 20) for i in range(6)]
        boxes += [box(145, 213, y0=700 - i * 20) for i in range(6)]
        assert len(split_columns(boxes, PAGE_WIDTH)) == 1

    def test_a_gutter_at_the_margin_is_ignored(self):
        """A gap out at the left margin is a margin, not a column break."""
        boxes = [box(30, 100, y0=700 - i * 20) for i in range(5)]
        boxes += [box(500, 580, y0=700 - i * 20) for i in range(5)]
        assert len(split_columns(boxes, PAGE_WIDTH)) == 1

    def test_too_few_boxes_is_a_single_column(self):
        assert len(split_columns([box(72, 100), box(330, 400)], PAGE_WIDTH)) == 1

    def test_a_lopsided_split_is_rejected(self):
        """One box on the right is a stray, not a column."""
        boxes = [box(72, 140, y0=700 - i * 20) for i in range(6)]
        boxes.append(box(400, 460, y0=600))
        assert len(split_columns(boxes, PAGE_WIDTH)) == 1

    def test_threshold_is_documented_and_used(self):
        assert MIN_GUTTER_POINTS >= 12, (
            "below ~12pt, ordinary word spacing starts registering as a gutter"
        )
