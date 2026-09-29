"""
Resumable, page-bounded ingestion.

The design constraint is that nothing holds a long-lived worker, because
Render Free has no broker and the browser drives progress. So ingest is a pure
function of (document, cursor) -> new state, safe to call repeatedly and safe
to call after a cold start or a mid-ingest deploy. See ingestion.md.

Three invariants carry that guarantee:

1. **The cursor is a row, not a variable.** It lives on `Document.ingest_cursor`
   so a restarted process reads the last committed position instead of starting
   over. A killed ingest loses at most one uncommitted batch.
2. **One transaction per batch.** Pages, chunks, and the cursor advance together.
   A crash between them is not representable.
3. **Upserts, keyed by uniqueness.** `Page` is unique on (document, page_number)
   and `Chunk` on (page, ordinal), so reprocessing a range converges instead of
   duplicating. Retry is therefore always safe.
"""

from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from api.chunking import chunk_page
from api.embeddings import embed_texts
from api.models import Chunk, Document, Library, Page, Profile
from api.parsing import parse_document

logger = logging.getLogger(__name__)

PAGES_PER_BATCH = 5


class IngestError(Exception):
    """Raised for conditions the caller turns into a user-visible message."""


class UploadMissing(IngestError):
    """The object is absent or too large, so there is nothing to parse."""


@dataclass
class IngestResult:
    document_id: str
    status: str
    cursor: int
    pages_written: int
    chunks_written: int
    done: bool
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "status": self.status,
            "cursor": self.cursor,
            "pages_written": self.pages_written,
            "chunks_written": self.chunks_written,
            "done": self.done,
            "error": self.error,
        }


def _download_to_temp(document: Document) -> pathlib.Path:
    """
    Fetch the file from Supabase Storage into a local temp path.

    `unstructured` needs a real file on disk; it will not take a stream. The
    temp file is deleted by the caller. Downloading per batch is deliberate:
    Render's filesystem is ephemeral, so a cache would be a lie about what the
    next request will find.

    The size is re-checked here rather than trusted from the create request. A
    signed PUT URL cannot enforce a Content-Length, so the `size_bytes` the
    client declared is only a claim; the object itself is the fact.
    """
    import tempfile

    from django.conf import settings as django_settings
    from django.core.files.storage import default_storage

    try:
        actual_size = default_storage.size(document.storage_path)
    except (FileNotFoundError, NotImplementedError, OSError) as exc:
        raise UploadMissing(
            "The upload did not finish. Please upload the file again."
        ) from exc

    if actual_size > django_settings.MAX_UPLOAD_BYTES:
        limit_mb = django_settings.MAX_UPLOAD_BYTES // (1024 * 1024)
        raise UploadMissing(f"The uploaded file is larger than {limit_mb}MB.")

    suffix = pathlib.Path(document.filename).suffix or ".bin"
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    handle.close()
    path = pathlib.Path(handle.name)
    try:
        with default_storage.open(document.storage_path, "rb") as remote:
            path.write_bytes(remote.read())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def _pending_pages(document: Document, parsed) -> list:
    """
    Pages strictly after the cursor, capped at one batch.

    The `<= ingest_cursor` skip is what makes resume cheap: a 40-page document
    still only ever works on the next five pages. Re-parsing happens either way
    (the parser is stateless), but no rows are rewritten.
    """
    return [p for p in parsed.pages if p.page_number > document.ingest_cursor][
        :PAGES_PER_BATCH
    ]


@transaction.atomic
def ingest_batch(
    document_id,
    owner: Profile,
    filename_override: pathlib.Path | None = None,
) -> IngestResult:
    """
    Advance one document by up to PAGES_PER_BATCH pages.

    `filename_override` lets tests ingest a fixture from disk without going
    through Supabase Storage. It is not exposed over HTTP.
    """
    document = (
        Document.objects.select_related("library")
        .filter(id=document_id, library__owner=owner)
        .first()
    )
    if document is None:
        raise IngestError("Document not found.")

    if document.status == Document.STATUS_FAILED:
        return IngestResult(
            document_id=str(document.id),
            status=document.status,
            cursor=document.ingest_cursor,
            pages_written=0,
            chunks_written=0,
            done=True,
            error=document.error,
        )
    if document.status == Document.STATUS_READY:
        return IngestResult(
            document_id=str(document.id),
            status=document.status,
            cursor=document.ingest_cursor,
            pages_written=0,
            chunks_written=0,
            done=True,
        )

    document.status = Document.STATUS_PARSING
    document.error = None
    document.save(update_fields=["status", "error"])

    path = filename_override
    if path is None:
        try:
            path = _download_to_temp(document)
        except UploadMissing as exc:
            # A missing or oversized object is a document-level failure with a
            # message the user can act on, not a 404. The upload never landed.
            return _fail(document, str(exc))

    try:
        parsed = parse_document(path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Parse failed for document %s", document.id)
        return _fail(document, f"Could not read the file: {exc}")
    finally:
        if filename_override is None:
            path.unlink(missing_ok=True)

    if not parsed.pages:
        return _fail(document, "No readable text found. Scanned PDFs need OCR, which is not supported yet.")

    batch = _pending_pages(document, parsed)
    if not batch:
        # Cursor is already at or past the last page. Normal completion.
        return _finish(document, parsed)

    library: Library = document.library

    # Build every chunk first so they embed in a single batched call. One call
    # per ingest is the whole point: per-chunk calls would be 40x the overhead
    # for the same result.
    drafts_by_page: list[tuple[Page, list]] = []
    for parsed_page in batch:
        drafts = chunk_page(parsed_page.text)
        if not drafts:
            continue
        page, _ = Page.objects.update_or_create(
            document=document,
            page_number=parsed_page.page_number,
            defaults={
                "text": parsed_page.text,
                "char_len": parsed_page.char_len,
                "heading_path": parsed_page.heading_path,
            },
        )
        drafts_by_page.append((page, drafts))

    if not drafts_by_page:
        return _fail(document, "Pages contained no indexable text.")

    flat = [draft for _, drafts in drafts_by_page for draft in drafts]
    vectors = embed_texts([draft.text for draft in flat])

    chunks_written = 0
    index = 0
    for page, drafts in drafts_by_page:
        for draft in drafts:
            Chunk.objects.update_or_create(
                page=page,
                ordinal=draft.ordinal,
                defaults={
                    "document": document,
                    "library": library,
                    "page_number": page.page_number,
                    "text": draft.text,
                    "heading_path": page.heading_path,
                    "token_count": draft.token_count,
                    "embedding": vectors[index].tolist(),
                },
            )
            index += 1
            chunks_written += 1

    # The cursor moves only now, inside the same transaction as the rows it
    # describes. If anything above raised, this never commits and the next call
    # redoes the batch harmlessly.
    document.ingest_cursor = batch[-1].page_number
    document.embed_model = settings.EMBED_MODEL
    document.page_count = parsed.source_page_count or len(parsed.pages)

    remaining = any(p.page_number > document.ingest_cursor for p in parsed.pages)
    if remaining:
        document.status = Document.STATUS_INDEXING
    else:
        document.status = Document.STATUS_READY
    document.save(
        update_fields=["ingest_cursor", "embed_model", "page_count", "status"]
    )

    return IngestResult(
        document_id=str(document.id),
        status=document.status,
        cursor=document.ingest_cursor,
        pages_written=len(drafts_by_page),
        chunks_written=chunks_written,
        done=document.status == Document.STATUS_READY,
    )


def _finish(document: Document, parsed) -> IngestResult:
    document.status = Document.STATUS_READY
    document.page_count = parsed.source_page_count or len(parsed.pages)
    document.embed_model = settings.EMBED_MODEL
    document.save(update_fields=["status", "page_count", "embed_model"])
    return IngestResult(
        document_id=str(document.id),
        status=document.status,
        cursor=document.ingest_cursor,
        pages_written=0,
        chunks_written=0,
        done=True,
    )


def _fail(document: Document, message: str) -> IngestResult:
    """Terminal failure. The error is shown to the user verbatim."""
    document.status = Document.STATUS_FAILED
    document.error = message
    document.save(update_fields=["status", "error"])
    return IngestResult(
        document_id=str(document.id),
        status=Document.STATUS_FAILED,
        cursor=document.ingest_cursor,
        pages_written=0,
        chunks_written=0,
        done=True,
        error=message,
    )


def ingest_to_completion(
    document_id,
    owner: Profile,
    max_batches: int = 200,
    filename_override: pathlib.Path | None = None,
) -> IngestResult:
    """Loop batches until done. Used by the CLI check and by tests."""
    result = IngestResult(str(document_id), "", 0, 0, 0, done=False)
    for _ in range(max_batches):
        result = ingest_batch(document_id, owner, filename_override=filename_override)
        if result.done:
            return result
    raise IngestError("Ingest did not complete within the batch limit.")
