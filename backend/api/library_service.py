"""Creating and moving documents through the pipeline.

Two things live here that do not belong in a view or a model:

  * provisioning a user's default library, which has to happen exactly once and
    has to survive two concurrent first requests;
  * validating stage transitions, which is a rule about the pipeline rather than
    about storage.

Views call into this module. Nothing else should write a Document or move its
stage, so the invariants hold in one place.
"""

from __future__ import annotations

import logging

from django.db import IntegrityError, transaction
from django.db.models import Count

from api.auth import SupabasePrincipal
from api.models import STAGE_ORDER, TERMINAL_STAGES, Document, DocumentStage, Library, Profile

logger = logging.getLogger(__name__)

DEFAULT_LIBRARY_NAME = "My library"


class StageTransitionError(Exception):
    """A stage change that the pipeline does not allow."""


class NotOwnedError(Exception):
    """The caller asked for a row that belongs to somebody else."""


def _ensure_profile(principal: SupabasePrincipal) -> Profile:
    """The caller's profile row, created on first use.

    Ownership is a foreign key to Profile, so anything that writes a Library or
    a Document needs the row to exist. In the request path the session has
    already been verified, which creates it, but relying on that ordering makes
    this module fail with a foreign key error if it is ever called first.
    """
    profile, _ = Profile.objects.get_or_create(id=principal.id, defaults={"email": principal.email})
    return profile


def get_or_create_default_library(principal: SupabasePrincipal) -> Library:
    """Return the caller's default library, creating it if absent.

    Two concurrent first requests can both miss and both try to insert. The
    partial unique index on (owner, is_default) turns the loser into an
    IntegrityError, so rather than letting that surface, the loser re-reads the
    row the winner wrote. Without this, a user who signs in while two requests
    are in flight sees a 500.
    """
    existing = Library.objects.filter(owner_id=principal.id, is_default=True).first()
    if existing is not None:
        return existing

    profile = _ensure_profile(principal)

    try:
        with transaction.atomic():
            return Library.objects.create(
                owner=profile,
                name=DEFAULT_LIBRARY_NAME,
                is_default=True,
            )
    except IntegrityError:
        # Lost the race. The winner's row is the one to use.
        winner = Library.objects.filter(owner_id=principal.id, is_default=True).first()
        if winner is None:
            raise
        return winner


def create_document(principal: SupabasePrincipal, library: Library, **fields) -> Document:
    """Create a document owned by `principal` inside `library`.

    `owner` is derived from the principal rather than accepted from the caller,
    so a request cannot place a document in someone else's account by sending a
    different owner id. The library is checked as well, because a foreign
    library is just as much a way out of the caller's own account: without this
    a caller could write a document into a library they cannot see, and the
    `owner` column would then disagree with the library it lives in.
    """
    if str(library.owner_id) != str(principal.id):
        raise NotOwnedError("that library belongs to another account")

    profile = _ensure_profile(principal)
    return Document.objects.create(owner=profile, library=library, **fields)


def advance_stage(document: Document, target: DocumentStage) -> Document:
    """Move a document to `target`, or raise if that is not allowed.

    Allowed: forwards through the pipeline, any stage to failed, and failed back
    to queued for an explicit retry. Rejected: skipping forwards, and moving out
    of a terminal state except for a retry of a failure.

    A retry is the one backward move allowed, and it resets the error so a
    document that succeeds after a retry does not keep advertising the old
    failure.
    """
    current = document.stage
    is_retry = current == DocumentStage.FAILED and target == DocumentStage.QUEUED

    if is_retry:
        document.stage = target
        document.error_message = ""
        document.save(update_fields=["stage", "error_message", "updated_at"])
        return document

    if current in TERMINAL_STAGES:
        raise StageTransitionError(f"cannot leave terminal stage {current!r} for {target!r}")

    if target == DocumentStage.FAILED:
        # Any stage may fail, including from any point.
        document.stage = target
        document.save(update_fields=["stage", "updated_at"])
        return document

    current_position = STAGE_ORDER.index(current)
    target_position = STAGE_ORDER.index(target)

    # Exactly one step forwards. Allowing any larger jump would let a bug that
    # skips embedding mark a document ready with no embeddings in the database,
    # and the failure would only show up as an uncited answer much later.
    if target_position != current_position + 1:
        raise StageTransitionError(
            f"cannot move from {current!r} to {target!r}: the pipeline advances one stage at a time"
        )

    document.stage = target
    document.save(update_fields=["stage", "updated_at"])
    return document


def fail_document(document: Document, reason: str) -> Document:
    """Mark a document failed, recording why."""
    document.stage = DocumentStage.FAILED
    # Truncated: this is surfaced to a user, and a traceback is not a message.
    document.error_message = reason[:2000]
    document.save(update_fields=["stage", "error_message", "updated_at"])
    return document


def document_counts_by_stage(documents) -> dict[str, int]:
    """Count documents per stage for the pipeline board.

    Every stage is present in the result, including the empty ones, so the board
    does not have to know which stages exist in order to render a column.
    """
    counts = {stage.value: 0 for stage in DocumentStage}
    rows = documents.values("stage").annotate(total=Count("id"))
    for row in rows:
        counts[row["stage"]] = row["total"]
    return counts


def is_ready_for_chat(document: Document) -> bool:
    """Whether a document's chunks can be cited in an answer."""
    return document.stage == DocumentStage.READY


def ready_documents(principal: SupabasePrincipal) -> list[Document]:
    """Documents with chunks available to cite.

    A document can reach `ready` before its chunks are queryable — a race
    between the stage write and the embedding commit — so readiness here means
    "ready and actually has chunks", not "the stage says ready".
    """
    from api import access

    return list(
        access.documents_for(principal)
        .filter(stage=DocumentStage.READY)
        .annotate(chunk_total=Count("chunks"))
        .filter(chunk_total__gt=0)
        .order_by("-created_at")
    )
