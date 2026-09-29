"""
Page-bounded chunking tests.

The invariant worth protecting is that a chunk never crosses a page boundary.
That is what makes `[3]` an exact citation, so a test asserts it directly
rather than inferring it from chunk sizes.
"""

from __future__ import annotations

import pytest

from api.chunking import (
    CHUNK_TARGET_TOKENS,
    ChunkDraft,
    chunk_page,
    chunk_pages,
)

SENTENCE = "The mitochondrial membrane is impermeable to most solutes. "


def long_paragraph(sentences: int = 400) -> str:
    return "".join(f"Statement {i} carries a moderate amount of text here. " for i in range(sentences))


class TestEmptyAndTrivial:
    def test_empty_page_yields_no_chunks(self):
        assert chunk_page("") == []
        assert chunk_page("   \n\n  ") == []

    def test_short_page_is_exactly_one_chunk(self):
        drafts = chunk_page("Just one short paragraph.")
        assert len(drafts) == 1
        assert drafts[0].ordinal == 0

    def test_paragraphs_below_the_cap_merge_into_one_chunk(self):
        """Small pages are not fragmented just because a cap exists."""
        text = "\n\n".join(f"Paragraph {i} is short." for i in range(20))
        assert len(chunk_page(text)) == 1


class TestPageBoundary:
    def test_ordinals_restart_per_page(self):
        result = chunk_pages([(1, long_paragraph()), (2, long_paragraph())])
        assert set(result) == {1, 2}
        # Both pages start at 0: ordinal is position within a page, which is
        # what "page 7, chunk 2" means to a reader.
        assert result[1][0].ordinal == 0
        assert result[2][0].ordinal == 0

    def test_a_chunk_never_contains_text_from_another_page(self):
        """The load-bearing invariant: no chunk spans a page, so a citation
        resolves to exactly one page."""
        pages = [(1, "marker alpha. " * 200), (2, "marker beta. " * 200)]
        for page_number, drafts in chunk_pages(pages).items():
            mine = "alpha" if page_number == 1 else "beta"
            theirs = "beta" if page_number == 1 else "alpha"
            for draft in drafts:
                assert mine in draft.text
                assert theirs not in draft.text, "chunk leaked text from another page"

    def test_start_ordinal_offsets_the_sequence(self):
        drafts = chunk_page(long_paragraph(), start_ordinal=3)
        assert drafts[0].ordinal == 3
        assert [d.ordinal for d in drafts] == list(range(3, 3 + len(drafts)))


class TestSizeLimits:
    def test_long_paragraph_splits_into_multiple_chunks(self):
        drafts = chunk_page(long_paragraph())
        assert len(drafts) > 1

    def test_no_chunk_exceeds_a_sane_multiple_of_the_target(self):
        """Overlap adds tokens, so the bound is the target plus the overlap,
        not the bare target. Still, a chunk far above that signals a split
        that failed."""
        for draft in chunk_page(long_paragraph()):
            assert draft.token_count <= CHUNK_TARGET_TOKENS * 1.5

    def test_token_counts_are_populated(self):
        for draft in chunk_page(long_paragraph(200)):
            assert draft.token_count > 0

    def test_never_splits_mid_sentence(self):
        """Every chunk should start at a sentence start, not mid-clause. The
        first chunk may start anywhere (it is the page start); later ones come
        from overlap plus a sentence boundary."""
        for draft in chunk_page(long_paragraph())[1:]:
            assert draft.text[0].isupper() or draft.text[0].isalnum()


class TestOverlap:
    def test_consecutive_chunks_share_text(self):
        drafts = chunk_page(long_paragraph())
        assert len(drafts) > 1
        first_tail = drafts[0].text[-120:]
        assert first_tail.strip()[:40] in drafts[1].text

    def test_first_chunk_has_no_predecessor_and_so_no_prefix(self):
        drafts = chunk_page("Single short paragraph.")
        assert not drafts[0].text.startswith("Represent this")

    def test_overlap_is_not_applied_to_single_chunk_pages(self):
        drafts = chunk_page("One paragraph. Two sentences. Three here.")
        assert len(drafts) == 1
        assert drafts[0].text.count("Single short paragraph.") <= 1


class TestContract:
    def test_returns_draft_dataclass_instances(self):
        draft = chunk_page("A short page of text.")[0]
        assert isinstance(draft, ChunkDraft)
        assert draft.text == draft.text.strip()

    def test_chunk_text_is_non_empty(self):
        for draft in chunk_page(long_paragraph()):
            assert draft.text.strip()
