from __future__ import annotations

import logging

from django.db import IntegrityError, transaction
from django.db.models import Count

from api.auth import SupabasePrincipal
from api.models import STAGE_ORDER, TERMINAL_STAGES, Document, DocumentStage, Library, Profile

logger = logging.getLogger(__name__)

DEFAULT_LIBRARY_NAME = "My library"


class StageTransitionError(Exception):
    pass


class NotOwnedError(Exception):
    pass


def _ensure_profile(principal: SupabasePrincipal) -> Profile:
    profile, _ = Profile.objects.get_or_create(id=principal.id, defaults={"email": principal.email})
    return profile


def get_or_create_default_library(principal: SupabasePrincipal) -> Library:
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
    if str(library.owner_id) != str(principal.id):
        raise NotOwnedError("that library belongs to another account")

    profile = _ensure_profile(principal)
    return Document.objects.create(owner=profile, library=library, **fields)


def advance_stage(document: Document, target: DocumentStage) -> Document:
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

    # Exactly one step forwards; no stage jump may skip embedding.
    if target_position != current_position + 1:
        raise StageTransitionError(
            f"cannot move from {current!r} to {target!r}: the pipeline advances one stage at a time"
        )

    document.stage = target
    document.save(update_fields=["stage", "updated_at"])
    return document


def fail_document(document: Document, reason: str) -> Document:
    document.stage = DocumentStage.FAILED
    # Truncated: this is surfaced to a user, and a traceback is not a message.
    document.error_message = reason[:2000]
    document.save(update_fields=["stage", "error_message", "updated_at"])
    return document


def document_counts_by_stage(documents) -> dict[str, int]:
    counts = {stage.value: 0 for stage in DocumentStage}
    rows = documents.values("stage").annotate(total=Count("id"))
    for row in rows:
        counts[row["stage"]] = row["total"]
    return counts


def is_ready_for_chat(document: Document) -> bool:
    return document.stage == DocumentStage.READY


def ready_documents(principal: SupabasePrincipal) -> list[Document]:
    from api import access

    return list(
        access.documents_for(principal)
        .filter(stage=DocumentStage.READY)
        .annotate(chunk_total=Count("chunks"))
        .filter(chunk_total__gt=0)
        .order_by("-created_at")
    )
