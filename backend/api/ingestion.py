from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import timedelta

from django.conf import settings
from django.db import connections, transaction
from django.utils import timezone

from api import chunking, library_service, parsing, storage
from api.embedding_client import EmbeddingError, embed_texts
from api.library_service import StageTransitionError, advance_stage
from api.models import Chunk, Document, DocumentStage

logger = logging.getLogger(__name__)

#: Chunks written per database batch; one transaction per batch, not one per document.
WRITE_BATCH_SIZE = 100

#: One fixed key; every process that ingests must take the same lock.
WORKER_LOCK_KEY = 0x526576694121  # b"ReviA!"


@contextmanager
def worker_lock():
    conn = connections["default"]

    # SQLite (the test suite) has no advisory locks.
    if conn.vendor != "postgresql":
        yield True
        return

    with conn.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [WORKER_LOCK_KEY])
        acquired = bool(cursor.fetchone()[0])

    try:
        yield acquired
    finally:
        if acquired:
            with conn.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [WORKER_LOCK_KEY])


class IngestionError(Exception):
    def __init__(self, reason: str, *, code: str = "ingestion_failed", retryable: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.code = code
        self.retryable = retryable


def ingest_document(document: Document) -> Document:
    try:
        pages = _parse(document)
        chunks = _split(document, pages)
        _write_chunks(document, chunks)
        _embed(document)
    except IngestionError as exc:
        _fail(document, exc.reason)
        raise
    except Exception as exc:
        logger.exception("Ingestion of document %s raised an unexpected error", document.id)
        _fail(document, f"Ingestion failed unexpectedly ({type(exc).__name__}).")
        raise IngestionError(
            f"Ingestion failed unexpectedly ({type(exc).__name__}).", code="internal_error"
        ) from exc

    return document


def _parse(document: Document) -> list[parsing.ExtractedPage]:
    if not document.storage_path:
        raise IngestionError(
            "This document's file is not in storage.", code="missing_file"
        )

    advance_stage(document, DocumentStage.PARSING)
    logger.info("Document %s (%s): parsing", document.id, document.filename)

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
    logger.info("Document %s: %d page(s) extracted", document.id, len(pages))

    return pages


def _split(document: Document, pages: list[parsing.ExtractedPage]) -> list[chunking.TextChunk]:
    advance_stage(document, DocumentStage.CHUNKING)

    try:
        return chunking.chunk_document(pages)
    except chunking.DocumentIsEmptyError as exc:
        raise IngestionError(str(exc), code="no_text") from exc


def _write_chunks(document: Document, chunks: list[chunking.TextChunk]) -> None:
    Chunk.objects.filter(document=document).delete()

    rows = [
        Chunk(
            owner_id=document.owner_id,
            document=document,
            ordinal=chunk.ordinal,
            page_number=chunk.page_number,
            content=chunk.content,
            heading_path=chunk.heading_path,
            token_count=chunk.estimated_tokens(),
        )
        for chunk in chunks
    ]

    with transaction.atomic():
        Chunk.objects.bulk_create(rows, batch_size=WRITE_BATCH_SIZE)

    logger.info("Wrote %d chunks for document %s", len(rows), document.id)


def _embed(document: Document) -> None:
    advance_stage(document, DocumentStage.EMBEDDING)

    # Ordered by ordinal, so embedding and the vector write-back see one order.
    chunks = list(Chunk.objects.filter(document=document).order_by("ordinal"))
    if not chunks:
        raise IngestionError("This document produced no text to index.", code="no_text")

    logger.info("Document %s: embedding %d chunk(s)", document.id, len(chunks))

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
    logger.info("Document %s: ready", document.id)


def _fail(document: Document, reason: str) -> None:
    logger.warning("Document %s marked failed: %s", document.id, reason)
    try:
        library_service.fail_document(document, reason)
    except StageTransitionError:
        logger.warning(
            "Document %s could not be moved to failed from %s",
            document.id,
            document.stage,
        )


def ingest_pending(limit: int = 10) -> dict[str, int]:
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
                try:
                    library_service.advance_stage(document, DocumentStage.QUEUED)
                except StageTransitionError:
                    failed += 1
                    continue
                document.error_message = exc.reason[:2000]
                document.save(update_fields=["error_message", "updated_at"])
                logger.info("Document %s requeued: %s", document.id, exc.reason[:120])
                retried += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    return {
        "attempted": len(queued),
        "ready": ready,
        "failed": failed,
        "retried": retried,
        "reaped": reaped,
    }

#: Fallback when PIPELINE_STALLED_SECONDS is not set.
STALLED_AFTER_SECONDS = 15 * 60


def stalled_after_seconds() -> int:
    return int(getattr(settings, "PIPELINE_STALLED_SECONDS", STALLED_AFTER_SECONDS))


def _reap_stalled() -> int:
    cutoff = timezone.now() - timedelta(seconds=stalled_after_seconds())
    stalled = Document.objects.filter(
        stage__in=[DocumentStage.PARSING, DocumentStage.CHUNKING, DocumentStage.EMBEDDING],
        updated_at__lt=cutoff,
    )

    count = stalled.count()
    if count:
        logger.warning("Returning %d stalled document(s) to the queue", count)
        stalled.update(
            stage=DocumentStage.QUEUED,
            error_message="",
            updated_at=timezone.now(),
        )
    return count
