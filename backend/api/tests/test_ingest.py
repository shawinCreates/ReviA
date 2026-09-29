"""
Ingest tests.

The behaviours that matter are the ones a user would only discover as a bug in
production: a retried batch duplicating rows, a cold start losing progress, and
one user's document being ingestible by another. Those get direct tests.
"""

from __future__ import annotations

import pathlib
import uuid

import pytest

from api.ingest import IngestError, ingest_batch, ingest_to_completion
from api.models import Chunk, Document, Library, Page, Profile

FIXTURES = pathlib.Path(__file__).resolve().parents[2] / "fixtures"

pytestmark = pytest.mark.django_db


def fixture(name: str) -> pathlib.Path:
    path = FIXTURES / name
    if not path.exists():  # pragma: no cover
        pytest.skip(f"fixture {name} missing; run make_fixtures.py")
    return path


@pytest.fixture
def owner(db):
    return Profile.objects.create(
        id=uuid.uuid4(), email="ingest-owner@example.com"
    )


@pytest.fixture
def intruder(db):
    return Profile.objects.create(id=uuid.uuid4(), email="intruder@example.com")


@pytest.fixture
def library(owner):
    return Library.objects.create(owner=owner, title="Papers")


def make_document(library: Library, name: str) -> Document:
    return Document.objects.create(
        library=library,
        filename=name,
        storage_path=f"{library.id}/{name}",
        mime="application/pdf",
        size_bytes=1234,
    )


class TestHappyPath:
    def test_small_document_ingests_in_one_batch_and_is_ready(self, owner, library):
        doc = make_document(library, "notes.md")
        result = ingest_batch(doc.id, owner, filename_override=fixture("notes.md"))
        doc.refresh_from_db()

        assert result.done
        assert result.status == Document.STATUS_READY
        assert doc.page_count == 1
        assert Page.objects.filter(document=doc).count() == 1
        assert Chunk.objects.filter(document=doc).count() >= 1

    def test_every_chunk_is_linked_to_a_page_and_library(self, owner, library):
        doc = make_document(library, "notes.md")
        ingest_batch(doc.id, owner, filename_override=fixture("notes.md"))

        for chunk in Chunk.objects.filter(document=doc):
            assert chunk.page_id is not None
            assert chunk.page.document_id == doc.id
            assert chunk.library_id == library.id
            assert chunk.page_number == chunk.page.page_number
            assert len(chunk.embedding) == 384
            assert chunk.token_count > 0

    def test_embedding_model_is_recorded(self, owner, library):
        """Retrieval must be able to tell which model wrote a vector."""
        doc = make_document(library, "notes.md")
        ingest_batch(doc.id, owner, filename_override=fixture("notes.md"))
        doc.refresh_from_db()
        assert doc.embed_model == "BAAI/bge-small-en-v1.5"

    def test_calling_ready_again_is_a_no_op(self, owner, library):
        doc = make_document(library, "notes.md")
        ingest_batch(doc.id, owner, filename_override=fixture("notes.md"))
        before = Chunk.objects.filter(document=doc).count()

        result = ingest_batch(doc.id, owner, filename_override=fixture("notes.md"))
        assert result.done
        assert result.chunks_written == 0
        assert Chunk.objects.filter(document=doc).count() == before


class TestPageAttribution:
    def test_markers_land_on_the_right_pages(self, owner, library):
        """The phase 1 gate: a marker written on page N must be retrievable as
        page N, not merely present somewhere in the document."""
        doc = make_document(library, "single_column.pdf")
        ingest_to_completion(doc.id, owner, filename_override=multipage_pdf)

        pages = {
            p.page_number: p.text
            for p in Page.objects.filter(document=doc)
        }
        for page_number, text in pages.items():
            assert f"PAGEMARKER-SINGLE-{page_number}" in text

    def test_page_count_matches_the_number_of_pages_written(
        self, owner, library, multipage_pdf
    ):
        doc = make_document(library, "multipage.pdf")
        ingest_to_completion(doc.id, owner, filename_override=multipage_pdf)
        doc.refresh_from_db()
        assert doc.page_count == Page.objects.filter(document=doc).count()
        assert doc.page_count == 9

    def test_multi_page_document_advances_the_cursor(
        self, owner, library, multipage_pdf
    ):
        doc = make_document(library, "multipage.pdf")
        result = ingest_batch(doc.id, owner, filename_override=multipage_pdf)
        assert result.cursor == 5
        assert result.status in (
            Document.STATUS_INDEXING,
            Document.STATUS_READY,
        )


class TestIdempotency:
    def test_reprocessing_a_range_does_not_duplicate_pages(
        self, owner, library, multipage_pdf
    ):
        doc = make_document(library, "multipage.pdf")
        ingest_to_completion(doc.id, owner, filename_override=multipage_pdf)
        pages_before = Page.objects.filter(document=doc).count()
        chunks_before = Chunk.objects.filter(document=doc).count()

        # Force a rewind, as a crashed transaction that advanced the cursor in
        # memory but never committed would.
        Document.objects.filter(id=doc.id).update(ingest_cursor=0)
        Document.objects.filter(id=doc.id).update(status=Document.STATUS_PARSING)
        ingest_to_completion(doc.id, owner, filename_override=multipage_pdf)

        assert Page.objects.filter(document=doc).count() == pages_before
        assert Chunk.objects.filter(document=doc).count() == chunks_before

    def test_chunks_are_unique_per_page_ordinal(self, owner, library):
        doc = make_document(library, "notes.md")
        ingest_batch(doc.id, owner, filename_override=fixture("notes.md"))

        pairs = list(
            Chunk.objects.filter(document=doc).values_list("page_id", "ordinal")
        )
        assert len(pairs) == len(set(pairs))


@pytest.fixture(scope="module")
def multipage_pdf(tmp_path_factory) -> pathlib.Path:
    """
    A 9-page PDF, so that a 5-page batch genuinely needs two calls.

    The committed 3-page fixture fits in one batch, which would make every
    resume assertion here vacuous. Batch size is a setting, so the test builds
    a document that is guaranteed to exceed it rather than depending on the
    fixture's length.
    """
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    path = tmp_path_factory.mktemp("ingest") / "multipage.pdf"
    c = canvas.Canvas(str(path), pagesize=LETTER)
    for page in range(1, 10):
        c.drawString(72, 720, f"PAGEMARKER-MULTI-{page}")
        c.drawString(72, 700, f"This is the body text of page {page}.")
        c.showPage()
    c.save()
    return path


class TestResume:
    def test_resume_completes_the_document_without_loss(self, owner, library, multipage_pdf):
        doc = make_document(library, "multipage.pdf")
        ingest_to_completion(doc.id, owner, filename_override=multipage_pdf)
        full = set(
            Page.objects.filter(document=doc).values_list("page_number", flat=True)
        )
        assert full == set(range(1, 10)), "all 9 pages should be stored"

        # Same document, cursor rewound as a killed ingest would leave it.
        Document.objects.filter(id=doc.id).update(ingest_cursor=0)
        Document.objects.filter(id=doc.id).update(status=Document.STATUS_PARSING)

        result = ingest_to_completion(doc.id, owner, filename_override=multipage_pdf)
        assert result.done
        assert set(
            Page.objects.filter(document=doc).values_list("page_number", flat=True)
        ) == full
        assert Chunk.objects.filter(document=doc).count() == 9, "no duplicate chunks"

    def test_a_kill_mid_ingest_resumes_from_the_cursor(
        self, owner, library, multipage_pdf
    ):
        """One batch, then the process 'dies'. The second call must pick up
        exactly where the cursor left off, not from zero."""
        doc = make_document(library, "multipage.pdf")
        first = ingest_batch(doc.id, owner, filename_override=multipage_pdf)

        assert not first.done
        assert first.cursor == 5, "first batch should cover pages 1-5"
        assert Page.objects.filter(document=doc).count() == 5

        second = ingest_batch(doc.id, owner, filename_override=multipage_pdf)
        assert second.done
        assert second.cursor == 9
        assert Page.objects.filter(document=doc).count() == 9

    def test_cursor_never_goes_backwards(self, owner, library, multipage_pdf):
        doc = make_document(library, "multipage.pdf")
        cursor = 0
        for _ in range(20):
            result = ingest_batch(doc.id, owner, filename_override=multipage_pdf)
            assert result.cursor >= cursor
            cursor = result.cursor
            if result.done:
                break
        assert result.done


class TestFailureModes:
    def test_unreadable_file_fails_with_a_message(self, owner, library):
        doc = make_document(library, "broken.pdf")
        broken = FIXTURES / "broken.pdf"
        broken.write_bytes(b"this is not a pdf at all")
        try:
            result = ingest_batch(doc.id, owner, filename_override=broken)
            assert result.status == Document.STATUS_FAILED
            assert result.error
        finally:
            broken.unlink(missing_ok=True)

    def test_failed_document_reports_its_error_and_stops(self, owner, library):
        doc = make_document(library, "notes.md")
        Document.objects.filter(id=doc.id).update(
            status=Document.STATUS_FAILED, error="Scanned PDF"
        )
        result = ingest_batch(doc.id, owner, filename_override=fixture("notes.md"))
        assert result.status == Document.STATUS_FAILED
        assert result.error == "Scanned PDF"
        assert Page.objects.filter(document=doc).count() == 0

    def test_empty_file_fails_rather_than_silently_succeeding(self, owner, library):
        doc = make_document(library, "empty.md")
        empty = FIXTURES / "empty.md"
        empty.write_text("")
        try:
            result = ingest_batch(doc.id, owner, filename_override=empty)
            assert result.status == Document.STATUS_FAILED
        finally:
            empty.unlink(missing_ok=True)


class TestAuthorization:
    def test_another_user_cannot_ingest(self, owner, library, intruder):
        doc = make_document(library, "notes.md")
        with pytest.raises(IngestError):
            ingest_batch(doc.id, intruder, filename_override=fixture("notes.md"))
        assert Page.objects.filter(document=doc).count() == 0

    def test_unknown_document_raises(self, owner):
        with pytest.raises(IngestError):
            ingest_batch(uuid.uuid4(), owner, filename_override=fixture("notes.md"))
