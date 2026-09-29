"""
PDF text extraction: one string per page, with columns in reading order.

Replaces `unstructured.partition.pdf`, which measured 968MB peak on a 3-page
fixture. pdfminer.six does the same job at 33MB — a 29x reduction, and the
difference between fitting and not fitting the 512MB target. See
fixtures/measure_parsers.py.

The one thing `unstructured` did better was two-column reading order, so that is
implemented here rather than given up. pdfminer emits text boxes in coordinate
order, which on a two-column page interleaves the columns line by line:

    left line 1, right line 1, left line 2, right line 2

That shreds sentences and retrieves badly. pdfminer does, however, give every
box a bounding box, so the gutter between columns can be found geometrically and
used to order the page column-first. See `split_columns`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# A gutter must be at least this wide (in points) to count as a column break.
# Narrower gaps are ordinary word spacing and full-width rules.
MIN_GUTTER_POINTS = 18.0

# The gutter must sit inside this fraction of the page width, otherwise it is a
# margin rather than a column break. A two-column paper splits near the middle.
MIN_GUTTER_FRACTION = 0.18
MAX_GUTTER_FRACTION = 0.82

# Boxes narrower than this are dropped: page numbers, stray rules, and artifacts
# contribute noise to embeddings without adding content.
MIN_BOX_WIDTH = 8.0
MIN_BOX_HEIGHT = 3.0


@dataclass
class TextBox:
    x0: float
    x1: float
    y0: float
    y1: float
    text: str


@dataclass
class PdfPage:
    number: int
    text: str
    column_count: int = 1


def _collect_boxes(layout) -> list[TextBox]:
    from pdfminer.layout import LTTextContainer

    boxes: list[TextBox] = []
    for element in layout:
        if not isinstance(element, LTTextContainer):
            continue
        text = element.get_text().strip()
        if not text:
            continue
        x0, y0, x1, y1 = element.bbox
        if (x1 - x0) < MIN_BOX_WIDTH or (y1 - y0) < MIN_BOX_HEIGHT:
            continue
        boxes.append(TextBox(x0=x0, x1=x1, y0=y0, y1=y1, text=text))
    return boxes


def split_columns(boxes: list[TextBox], page_width: float) -> list[list[TextBox]]:
    """
    Group boxes into columns and return them left to right.

    Finds the widest vertical gap that no box crosses and that sits in the middle
    band of the page. A real two-column layout leaves a gutter there; a
    single-column layout does not, and the widest gap it offers is ordinary word
    spacing or the space beside a full-width title.

    Returns a single group when no plausible gutter exists, so a one-column page
    is never misread as two.
    """
    if len(boxes) < 4:
        return [boxes]

    low = page_width * MIN_GUTTER_FRACTION
    high = page_width * MAX_GUTTER_FRACTION

    # Merge the boxes' x-intervals into a union, then look for a hole in it.
    # Working from the union matters: a single wide box (a full-width title)
    # otherwise hides the gutter underneath it, and sweeping raw left/right
    # edges measures the gap from the narrowest box instead of the widest.
    intervals = sorted((b.x0, b.x1) for b in boxes)
    merged: list[list[float]] = [list(intervals[0])]
    for x0, x1 in intervals[1:]:
        if x0 <= merged[-1][1] + 1.0:
            merged[-1][1] = max(merged[-1][1], x1)
        else:
            merged.append([x0, x1])

    best_gap: tuple[float, float, float] | None = None  # (width, start, end)
    for (start, end), (next_start, _next_end) in zip(merged, merged[1:]):
        width = next_start - end
        if width < MIN_GUTTER_POINTS:
            continue
        # The gutter has to sit in the middle band of the page. A gap out at a
        # margin is just a margin.
        if not (low <= end and next_start <= high):
            continue
        if best_gap is None or width > best_gap[0]:
            best_gap = (width, end, next_start)

    if best_gap is None:
        return [boxes]

    _, gutter_start, gutter_end = best_gap
    # A box belongs to the right column when it *starts* there. Testing the left
    # edge rather than the right one is what keeps a wide left-column line — or a
    # full-width title that stops inside the gutter — from being dropped or
    # misfiled. Anything not clearly in the right column stays left, so no box
    # is ever silently discarded.
    right = [b for b in boxes if b.x0 >= gutter_end - 1.0]
    left = [b for b in boxes if b.x0 < gutter_end - 1.0]
    if len(left) < 2 or len(right) < 2:
        return [boxes]
    return [left, right]


def _order(boxes: list[TextBox]) -> list[TextBox]:
    """
    Read order within a column: top to bottom, then left to right for ties.

    pdfminer's y grows upward, so descending y is descending vertical position.
    The small tolerance groups boxes on the same visual line, which stops a
    heading slightly offset from its body from jumping below it.
    """
    return sorted(boxes, key=lambda b: (-round(b.y1 / 3.0), b.x0))


def extract_pages(path) -> list[PdfPage]:
    """
    Extract every page of a PDF. Page numbers are 1-indexed and match what a
    reader sees, which is the whole contract the citation layer depends on.
    """
    from pdfminer.high_level import extract_pages as _extract
    from pdfminer.pdfpage import PDFPage as _PDFPage

    pages: list[PdfPage] = []
    for index, layout in enumerate(_extract(str(path)), start=1):
        boxes = _collect_boxes(layout)
        if not boxes:
            # An image-only page still exists and still occupies a page number.
            # Emitting it empty keeps citation numbering aligned with the file.
            pages.append(PdfPage(number=index, text=""))
            continue

        width = _page_width(layout)
        columns = split_columns(boxes, width)
        ordered: list[str] = []
        for column in columns:
            for box in _order(column):
                ordered.append(box.text)

        pages.append(
            PdfPage(number=index, text="\n".join(ordered), column_count=len(columns))
        )
    return pages


def _page_width(layout) -> float:
    """
    Page width in points, from the page's own bounding box.

    Needed so the gutter test is relative to the real page rather than to the
    text extent: a two-column page's text starts and ends near the margins, so
    using the text extent would shift every threshold.
    """
    try:
        x0, _, x1, _ = layout.bbox
        width = float(x1) - float(x0)
        if width > 1.0:
            return width
    except (AttributeError, TypeError, ValueError):  # pragma: no cover
        pass
    return 0.0
