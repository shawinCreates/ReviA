from __future__ import annotations

import pytest

from api.chunking import DocumentIsEmptyError, chunk_document
from api.parsing import ExtractedBlock, ExtractedPage


def body(text: str, *, page: int = 1) -> ExtractedBlock:
    return ExtractedBlock(text=text, level=None, page_number=page)


def heading(text: str, *, level: int = 1, page: int = 1) -> ExtractedBlock:
    return ExtractedBlock(text=text, level=level, page_number=page)


def page(number: int, *blocks: ExtractedBlock) -> ExtractedPage:
    return ExtractedPage(number=number, blocks=tuple(blocks))


def _long(prefix: str, *, count: int) -> str:
    return " ".join(f"{prefix} sentence number {index}." for index in range(count))


def test_a_heading_opens_a_chunk_and_names_its_path():
    chunks = chunk_document([page(1, heading("Introduction"), body("A short body of text."))])

    assert len(chunks) == 1
    assert chunks[0].heading_path == "Introduction"
    assert chunks[0].content.startswith("Introduction")


def test_nested_headings_build_a_path():
    chunks = chunk_document(
        [
            page(
                1,
                heading("2. Methods", level=1),
                heading("2.1 Data collection", level=2),
                body("We surveyed forty participants over three weeks."),
            )
        ]
    )

    assert chunks[0].heading_path == "2. Methods > 2.1 Data collection"
    assert "2. Methods" in chunks[0].content
    assert "2.1 Data collection" in chunks[0].content


def test_a_sibling_heading_replaces_the_previous_one():
    blocks = [
        heading("2. Methods", level=1),
        heading("2.1 Data", level=2),
        body("First body."),
        heading("2.2 Analysis", level=2),
        body("Second body."),
    ]

    chunks = chunk_document([page(1, *blocks)])
    paths = [chunk.heading_path for chunk in chunks]

    assert paths == ["2. Methods > 2.1 Data", "2. Methods > 2.2 Analysis"]


def test_chunks_do_not_merge_across_headings():
    blocks = [
        heading("One"),
        body("Body belonging to section one."),
        heading("Two"),
        body("Body belonging to section two."),
    ]

    chunks = chunk_document([page(1, *blocks)])

    assert len(chunks) == 2
    assert chunks[0].heading_path == "One"
    assert "section two" not in chunks[0].content
    assert chunks[1].heading_path == "Two"


def test_an_oversized_section_splits_and_every_piece_keeps_the_heading():
    blocks = [
        heading("Long section"),
        body(_long("Alpha", count=120), page=1),
        body(_long("Beta", count=120), page=2),
    ]

    chunks = chunk_document([page(1, *blocks)])

    assert len(chunks) > 1
    assert all(chunk.heading_path == "Long section" for chunk in chunks)
    assert all(chunk.content.startswith("Long section") for chunk in chunks)


def test_content_without_headings_falls_back_to_paragraphs():
    chunks = chunk_document([page(1, body("Just some prose. Nothing structured here."))])

    assert chunks[0].heading_path == ""


def test_a_heading_with_no_body_produces_no_chunk_on_its_own():
    blocks = [heading("Empty"), heading("Next"), body("Real content lives here.")]

    chunks = chunk_document([page(1, *blocks)])

    assert len(chunks) == 1
    assert chunks[0].heading_path == "Next"


def test_pages_are_tracked_on_the_chunk_that_starts_them():
    blocks = [
        heading("Travels", page=1),
        body(_long("First", count=100), page=1),
        body(_long("Second", count=100), page=2),
    ]

    chunks = chunk_document([page(1, *blocks)])

    assert chunks[0].page_number == 1
    assert chunks[-1].page_number == 2


def test_a_document_with_no_text_raises():
    with pytest.raises(DocumentIsEmptyError):
        chunk_document([page(1)])
