"""Ownership scoping, and the pipeline rules that protect it.

The service connects as the database owner, which bypasses RLS, so these helpers
are the only thing standing between one account's document and another account's
answer. A helper that looks right but filters on the wrong column is exactly the
failure this design invites, so the scoping is asserted rather than assumed.
"""

from __future__ import annotations

import uuid

import pytest

from api import access, library_service
from api.auth import SupabasePrincipal
from api.library_service import NotOwnedError, StageTransitionError
from api.models import Chunk, Document, DocumentStage, Library, Profile

pytestmark = pytest.mark.django_db


def _principal() -> SupabasePrincipal:
    return SupabasePrincipal(id=str(uuid.uuid4()), email=f"{uuid.uuid4().hex}@example.com")


def _document_for(principal: SupabasePrincipal, filename: str = "paper.pdf") -> Document:
    library = library_service.get_or_create_default_library(principal)
    return library_service.create_document(
        principal, library, filename=filename, storage_path=f"{principal.id}/{filename}"
    )


# --- access helpers --------------------------------------------------------------


def test_a_caller_sees_only_their_own_libraries():
    mine = _principal()
    theirs = _principal()
    my_library = library_service.get_or_create_default_library(mine)
    library_service.get_or_create_default_library(theirs)

    ids = set(access.libraries_for(mine).values_list("id", flat=True))

    assert ids == {my_library.id}


def test_a_caller_sees_only_their_own_documents():
    mine, theirs = _principal(), _principal()
    _document_for(mine, "mine.pdf")
    _document_for(theirs, "theirs.pdf")

    names = set(access.documents_for(mine).values_list("filename", flat=True))

    assert names == {"mine.pdf"}


def test_narrowing_documents_to_a_library_stays_inside_the_caller():
    mine, theirs = _principal(), _principal()
    _document_for(mine, "mine.pdf")
    _document_for(theirs, "theirs.pdf")

    their_library = access.libraries_for(theirs).get()
    mine_documents = access.documents_for(mine, library=their_library)

    # The library is not the caller's, so the combination matches nothing.
    # It must never widen the result to the other account's documents.
    assert list(mine_documents) == []


def test_chunks_are_scoped_to_their_owner():
    mine, theirs = _principal(), _principal()
    my_document = _document_for(mine, "mine.pdf")
    their_document = _document_for(theirs, "theirs.pdf")
    Chunk.objects.create(owner_id=mine.id, document=my_document, ordinal=1, content="mine")
    Chunk.objects.create(owner_id=theirs.id, document=their_document, ordinal=1, content="theirs")

    contents = set(access.chunks_for(mine).values_list("content", flat=True))

    assert contents == {"mine"}


# --- default library -------------------------------------------------------------


def test_the_default_library_is_created_once():
    principal = _principal()

    first = library_service.get_or_create_default_library(principal)
    second = library_service.get_or_create_default_library(principal)

    assert first.id == second.id
    assert Library.objects.filter(owner_id=principal.id).count() == 1


def test_the_default_library_creates_the_profile():
    principal = _principal()
    assert not Profile.objects.filter(pk=principal.id).exists()

    library_service.get_or_create_default_library(principal)

    assert Profile.objects.filter(pk=principal.id).exists()
    assert str(library_service.get_or_create_default_library(principal).owner_id) == principal.id


def test_creating_a_document_in_another_accounts_library_is_refused():
    mine, theirs = _principal(), _principal()
    their_library = library_service.get_or_create_default_library(theirs)

    with pytest.raises(NotOwnedError):
        library_service.create_document(mine, their_library, filename="intruder.pdf")

    assert Document.objects.count() == 0


# --- stage transitions -----------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (DocumentStage.QUEUED, DocumentStage.PARSING),
        (DocumentStage.PARSING, DocumentStage.CHUNKING),
        (DocumentStage.CHUNKING, DocumentStage.EMBEDDING),
        (DocumentStage.EMBEDDING, DocumentStage.READY),
    ],
)
def test_the_pipeline_advances_one_stage_at_a_time(start, target):
    document = _document_for(_principal())
    document.stage = start
    document.save(update_fields=["stage"])

    moved = library_service.advance_stage(document, target)

    assert moved.stage == target


@pytest.mark.parametrize(
    ("start", "target"),
    [
        # Skipping is how a document would end up "ready" with no embeddings.
        (DocumentStage.QUEUED, DocumentStage.READY),
        (DocumentStage.QUEUED, DocumentStage.CHUNKING),
        (DocumentStage.PARSING, DocumentStage.EMBEDDING),
        (DocumentStage.CHUNKING, DocumentStage.READY),
        # And backwards, which would undo work that has already been done.
        (DocumentStage.CHUNKING, DocumentStage.PARSING),
        (DocumentStage.READY, DocumentStage.QUEUED),
    ],
)
def test_skipping_and_rewinding_are_refused(start, target):
    document = _document_for(_principal())
    document.stage = start
    document.save(update_fields=["stage"])

    with pytest.raises(StageTransitionError):
        library_service.advance_stage(document, target)

    document.refresh_from_db()
    assert document.stage == start


def test_any_stage_can_fail_and_the_reason_is_kept():
    principal = _principal()
    document = _document_for(principal)
    document.stage = DocumentStage.CHUNKING
    document.save(update_fields=["stage"])

    failed = library_service.fail_document(document, "the file is not a PDF")

    assert failed.stage == DocumentStage.FAILED
    assert failed.error_message == "the file is not a PDF"


def test_a_failure_reason_is_truncated_because_a_user_reads_it():
    document = _document_for(_principal())

    failed = library_service.fail_document(document, "x" * 5000)

    assert len(failed.error_message) == 2000


def test_a_failed_document_can_be_retried_and_forgets_the_old_error():
    document = _document_for(_principal())
    library_service.fail_document(document, "transient network error")

    retried = library_service.advance_stage(document, DocumentStage.QUEUED)

    assert retried.stage == DocumentStage.QUEUED
    assert retried.error_message == ""


def test_a_ready_document_cannot_be_retried_or_failed_silently():
    document = _document_for(_principal())
    library_service.advance_stage(
        library_service.advance_stage(
            library_service.advance_stage(
                library_service.advance_stage(document, DocumentStage.PARSING),
                DocumentStage.CHUNKING,
            ),
            DocumentStage.EMBEDDING,
        ),
        DocumentStage.READY,
    )

    with pytest.raises(StageTransitionError):
        library_service.advance_stage(document, DocumentStage.QUEUED)


# --- readiness and counts --------------------------------------------------------


def test_only_documents_with_chunks_count_as_ready():
    ready_principal = _principal()
    document = _document_for(ready_principal)
    document.stage = DocumentStage.READY
    document.save(update_fields=["stage"])
    Chunk.objects.create(owner_id=ready_principal.id, document=document, ordinal=1, content="text")

    assert [d.id for d in library_service.ready_documents(ready_principal)] == [document.id]


def test_a_document_marked_ready_without_chunks_is_not_cited():
    principal = _principal()
    document = _document_for(principal)
    document.stage = DocumentStage.READY
    document.save(update_fields=["stage"])

    assert library_service.ready_documents(principal) == []


def test_stage_counts_include_the_empty_stages():
    principal = _principal()
    _document_for(principal, "one.pdf")
    second = _document_for(principal, "two.pdf")
    second.stage = DocumentStage.FAILED
    second.save(update_fields=["stage"])

    counts = library_service.document_counts_by_stage(access.documents_for(principal))

    assert counts[DocumentStage.QUEUED.value] == 1
    assert counts[DocumentStage.FAILED.value] == 1
    assert counts[DocumentStage.READY.value] == 0
    # Every stage is present, so the pipeline board can render a column per stage.
    assert set(counts) == {stage.value for stage in DocumentStage}
