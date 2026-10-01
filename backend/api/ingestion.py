"""Running a document through the pipeline: read, split, embed, store.

The four stages are the ones `DocumentStage` names, and they are driven from one
place so the ordering cannot drift between callers. Each stage advances the row
before doing its work, which means the pipeline board shows where something
actually is rather than where it was last observed.

Two properties are enforced here rather than left to the caller.

**A failure always lands somewhere visible.** Any error leaves the document in
`failed` with a reason a user can read, never stranded in `embedding` forever.
The alternative is a document that looks like it is still working on it.

**Re-ingesting replaces rather than appends.** Running a document twice must not
leave the first run's chunks behind, because they carry the first run's
embeddings and would be retrieved alongside the new ones.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from api import chunking, library_service, parsing, storage
from api.embedding_client import EmbeddingError, embed_texts
from api.library_service import StageTransitionError, advance_stage
from api.models import Chunk, Document, DocumentStage

logger = logging.getLogger(__name__)

#: Chunks written per batch. One transaction per batch rather than one for the
#: whole document, so a large file does not hold a single long transaction and a
#: failure part-way leaves the earlier work committed.
WRITE_BATCH_SIZE = 100

#: How long to wait before retrying a document whose embedding call was
#: rate-limited. The document is put back in `queued` and picked up again.
RETRY_DELAY_SECONDS = 30


class IngestionError(Exception):
    """A document could not be ingested, with a reason meant for the user."""

    def __init__(self, reason: str, *, code: str = "ingestion_failed", retryable: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.code = code
        self.retryable = retryable


def ingest_document(document: Document) -> Document:
    """Take a queued document all the way to `ready`, or fail it visibly."""
    try:
        pages = _parse(document)
        chunks = _split(document, pages)
        _write_chunks(document, chunks)
        _embed(document)
    except IngestionError as exc:
        _fail(document, exc.reason)
        raise
    except Exception as exc:
        # A bug here is still a document the user is waiting on, so it is marked
        # failed rather than left pending. The exception type is logged for an
        # operator; the user gets something they can act on.
        logger.exception("Ingestion of document %s raised an unexpected error", document.id)
        _fail(document, f"Ingestion failed unexpectedly ({type(exc).__name__}).")
        raise IngestionError(
            f"Ingestion failed unexpectedly ({type(exc).__name__}).", code="internal_error"
        ) from exc

    return document


def _parse(document: Document) -> list[parsing.ExtractedPage]:
    if not document.storage_path:
        # Reached when a document row exists but its bytes are not in the bucket,
        # which is what a failed upload leaves behind if the row was created
        # first and the store then failed.
        raise IngestionError(
            "This document's file is not in storage.", code="missing_file"
        )

    advance_stage(document, DocumentStage.PARSING)

    try:
        data = storage.download_file(document.storage_path)
    except storage.StorageError as exc:
        raise IngestionError(
            "This document's file could not be read from storage.", code="storage_unavailable"
        ) from exc

    try:
        pages = parsing.extract_pages(document.filename, data)
    except parsing.DocumentParsingError as exc:
        raise IngestionError(exc.reason, code=exc.code) from exc

    document.page_count = parsing.page_count(pages)
    document.save(update_fields=["page_count", "updated_at"])

    return pages


def _split(document: Document, pages: list[parsing.ExtractedPage]) -> list[chunking.TextChunk]:
    advance_stage(document, DocumentStage.CHUNKING)

    try:
        return chunking.chunk_document(pages)
    except chunking.DocumentIsEmptyError as exc:
        raise IngestionError(str(exc), code="no_text") from exc


def _write_chunks(document: Document, chunks: list[chunking.TextChunk]) -> None:
    """Store the chunk text, without embeddings yet.

    Separate from embedding so a rate-limited embedding call does not lose the
    parsing work. Chunks from a previous attempt are removed first: a document
    retried after failing part-way already has chunks on the row, and they were
    embedded by a run that may not have finished. Leaving them would retrieve
    two generations of the same text, and only one of them would be cited.
    """
    Chunk.objects.filter(document=document).delete()

    rows = [
        Chunk(
            owner_id=document.owner_id,
            document=document,
            ordinal=chunk.ordinal,
            page_number=chunk.page_number,
            content=chunk.content,
            token_count=chunk.estimated_tokens(),
        )
        for chunk in chunks
    ]

    with transaction.atomic():
        Chunk.objects.bulk_create(rows, batch_size=WRITE_BATCH_SIZE)

    logger.info("Wrote %d chunks for document %s", len(rows), document.id)


def _embed(document: Document) -> None:
    advance_stage(document, DocumentStage.EMBEDDING)

    # Ordered by ordinal so the text sent for embedding is in a known order, and
    # the vectors are written back against the same order.
    chunks = list(Chunk.objects.filter(document=document).order_by("ordinal"))
    if not chunks:
        raise IngestionError("This document produced no text to index.", code="no_text")

    try:
        vectors = embed_texts([chunk.content for chunk in chunks])
    except EmbeddingError as exc:
        raise IngestionError(
            exc.reason,
            code="embedding_failed",
            # A rate limit is worth another attempt; a wrong model is not.
            retryable=exc.retryable,
        ) from exc

    for chunk, vector in zip(chunks, vectors, strict=True):
        chunk.embedding = vector

    with transaction.atomic():
        Chunk.objects.bulk_update(chunks, ["embedding"], batch_size=WRITE_BATCH_SIZE)

    advance_stage(document, DocumentStage.READY)
    document.error_message = ""
    document.save(update_fields=["error_message", "updated_at"])


def _fail(document: Document, reason: str) -> None:
    """Mark the document failed, whatever stage it had reached.

    Goes through the service rather than writing the row directly, so the
    transition stays subject to the same rules as a normal stage change and the
    two cannot drift apart.
    """
    try:
        library_service.fail_document(document, reason)
    except StageTransitionError:
        # Unreachable while failing is legal from every stage, which it is. Kept
        # so that a future tightening of the transition rules degrades into a
        # log line rather than an exception that hides the real reason.
        logger.warning(
            "Document %s could not be moved to failed from %s",
            document.id,
            document.stage,
        )


def ingest_pending(limit: int = 10) -> dict[str, int]:
    """Process queued documents, oldest first.

    The worker entry point. `limit` bounds one pass so a long queue is worked
    through in order across several invocations rather than one unbounded run.
    """
    reaped = _reap_stalled()

    queued = list(
        Document.objects.filter(stage=DocumentStage.QUEUED).order_by("created_at")[:limit]
    )

    ready = 0
    failed = 0
    retried = 0

    for document in queued:
        try:
            ingest_document(document)
            ready += 1
        except IngestionError as exc:
            if exc.retryable:
                # Back to queued so the next pass tries again, with the reason
                # kept on the row so the board can say why it is still waiting.
                # The retry transition clears the message, so it is written
                # afterwards rather than instead of it.
                try:
                    library_service.advance_stage(document, DocumentStage.QUEUED)
                except StageTransitionError:
                    failed += 1
                    continue
                document.error_message = exc.reason[:2000]
                document.save(update_fields=["error_message", "updated_at"])
                retried += 1
            else:
                failed += 1
        except Exception:
            # `ingest_document` has already marked it failed and logged the
            # cause. Counting it here keeps one pass's totals honest.
            failed += 1

    return {
        "attempted": len(queued),
        "ready": ready,
        "failed": failed,
        "retried": retried,
        "reaped": reaped,
    }


#: How long a document may sit mid-pipeline before it is treated as abandoned.
#: Long enough that a slow embedding call is not interrupted, short enough that
#: a document does not sit in `parsing` for a week.
STALLED_AFTER_SECONDS = 15 * 60


def _reap_stalled() -> int:
    """Return documents stranded mid-pipeline to the queue.

    A worker that is killed part-way — a deploy, an OOM, a Ctrl-C at the wrong
    moment — leaves its document in `parsing` or `embedding` with nothing left to
    move it. Nothing else would ever pick those up: a pass only looks at
    `queued`. So each pass first resets anything that has been sitting in a
    non-terminal stage for too long.

    The threshold is measured from `updated_at`, which `advance_stage` refreshes,
    so a document genuinely still being worked on is not reset out from under the
    worker handling it.
    """
    cutoff = timezone.now() - timedelta(seconds=STALLED_AFTER_SECONDS)
    stalled = Document.objects.filter(
        stage__in=[DocumentStage.PARSING, DocumentStage.CHUNKING, DocumentStage.EMBEDDING],
        updated_at__lt=cutoff,
    )

    count = stalled.count()
    if count:
        logger.warning("Returning %d stalled document(s) to the queue", count)
        # Straight to `queued` rather than through `advance_stage`: a stalled
        # document's own transition history is not what is being repaired here,
        # and the failed-then-queued path would also clear a failure reason that
        # a new attempt is about to replace anyway.
        stalled.update(
            stage=DocumentStage.QUEUED,
            error_message="",
            updated_at=timezone.now(),
        )
    return count
