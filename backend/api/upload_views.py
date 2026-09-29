"""
Upload and ingest endpoints.

The flow is three calls, and the split exists because Django must never handle
file bytes:

    1. POST /api/documents          -> create the row, get a signed PUT URL
    2. PUT  <storage>              -> the browser uploads directly to Storage
    3. POST /api/documents/{id}/ingest -> parse five pages, embed, advance

The browser drives step 3 repeatedly until `done` is true. That is deliberate:
there is no worker to run it, and it means ingestion resumes for free when a tab
is reopened. See ingestion.md.
"""

from __future__ import annotations

import logging

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import storage as storage_api
from .errors import error_payload
from .ingest import IngestError, ingest_batch
from .models import Document, Library

logger = logging.getLogger(__name__)


class DocumentCreateView(APIView):
    """
    Create a document row and hand back a signed upload URL.

    The declared `size_bytes` is the client's claim, so it is validated against
    the limit but not trusted as fact. The real size is re-checked against the
    uploaded object at ingest time, because a signed PUT cannot enforce a length.
    """

    def post(self, request):
        profile = getattr(request, "profile", None)
        if profile is None:  # pragma: no cover - middleware guarantees this
            return Response(
                error_payload("unauthenticated", "No profile on the request."),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        body = request.data or {}
        library_id = str(body.get("library_id", ""))
        filename = str(body.get("filename", "")).strip()
        mime = str(body.get("mime", "")).strip()
        try:
            size_bytes = int(body.get("size_bytes", 0))
        except (TypeError, ValueError):
            return Response(
                error_payload("bad_request", "size_bytes must be a number."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not filename:
            return Response(
                error_payload("bad_request", "filename is required."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if mime not in settings.SUPPORTED_MIME_TYPES:
            return Response(
                error_payload(
                    "unsupported_type",
                    f"{mime or 'That file type'} is not supported.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if size_bytes <= 0:
            return Response(
                error_payload("bad_request", "The file is empty."),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if size_bytes > settings.MAX_UPLOAD_BYTES:
            limit_mb = settings.MAX_UPLOAD_BYTES // (1024 * 1024)
            return Response(
                error_payload("file_too_large", f"Files must be under {limit_mb}MB."),
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        library = Library.objects.filter(id=library_id, owner=profile).first()
        if library is None:
            # Same response for "does not exist" and "not yours". Distinguishing
            # them would confirm the existence of another user's library.
            return Response(
                error_payload("not_found", "Library not found."),
                status=status.HTTP_404_NOT_FOUND,
            )

        count = Document.objects.filter(library=library).count()
        if count >= settings.MAX_DOCS_PER_LIBRARY:
            return Response(
                error_payload(
                    "library_full",
                    f"A library holds at most {settings.MAX_DOCS_PER_LIBRARY} documents.",
                ),
                status=status.HTTP_409_CONFLICT,
            )

        path = storage_api.build_path(library.id, filename)
        document = Document.objects.create(
            library=library,
            filename=filename,
            storage_path=path,
            mime=mime,
            size_bytes=size_bytes,
            status=Document.STATUS_QUEUED,
        )

        try:
            upload_url = storage_api.presigned_upload_url(path, mime)
        except Exception as exc:  # noqa: BLE001
            # Deliberately broad. boto3 raises NoCredentialsError, EndpointConnectionError
            # and ClientError, none of which are StorageError, and all of them mean the
            # same thing to the user: uploads are down. The row is removed because a
            # document with no object can never be ingested and would count against
            # the library cap forever.
            document.delete()
            logger.error("Could not sign upload URL: %s: %s", type(exc).__name__, exc)
            return Response(
                error_payload("storage_unavailable", "Uploads are temporarily unavailable."),
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "id": str(document.id),
                "status": document.status,
                "filename": document.filename,
                "mime": document.mime,
                "size_bytes": document.size_bytes,
                "upload_url": upload_url,
                "storage_path": document.storage_path,
                "expires_in": storage_api.UPLOAD_URL_TTL_SECONDS,
                # The browser must send exactly this, or the signature fails.
                "upload_headers": {"Content-Type": mime},
            },
            status=status.HTTP_201_CREATED,
        )


class DocumentIngestView(APIView):
    """
    Advance one document by up to five pages. Idempotent.

    Called repeatedly by the browser until `done`. Ownership is enforced here
    rather than trusting the frontend, because a document id is a UUID and the
    ingest call is the expensive one.
    """

    def post(self, request, document_id):
        profile = getattr(request, "profile", None)
        if profile is None:  # pragma: no cover
            return Response(
                error_payload("unauthenticated", "No profile on the request."),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            result = ingest_batch(document_id, profile)
        except IngestError as exc:
            return Response(
                error_payload("not_found", str(exc)),
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ingest failed for %s", document_id)
            return Response(
                error_payload("ingest_failed", f"Ingest failed: {type(exc).__name__}"),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # A document that ended up `failed` is still a successful HTTP call: the
        # request did what it was asked, and the result reports the outcome. It
        # returns 200 with `status: "failed"` and a human-readable `error`.
        #
        # Returning 422 with an error envelope instead would be worse: the
        # frontend's generic error path would show "Ingest failed" and discard
        # the specific, actionable message ("The upload did not finish"). It
        # would also make `error` mean two different things across the API — an
        # object with a `code` here and a bare string there — and the frontend
        # switches on `code`. The browser drives this endpoint in a loop until
        # `done`, so it reads `status` and `error` off the result either way.
        return Response(result.as_dict(), status=status.HTTP_200_OK)


class DocumentDetailView(APIView):
    """
    Poll a document's ingest progress.

    Exists so the frontend can show a progress bar that survives a page reload:
    after a cold start the client re-reads this and resumes from `cursor`.
    """

    def get(self, request, document_id):
        profile = getattr(request, "profile", None)
        if profile is None:  # pragma: no cover
            return Response(
                error_payload("unauthenticated", "No profile on the request."),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        document = (
            Document.objects.filter(id=document_id, library__owner=profile)
            .select_related("library")
            .first()
        )
        if document is None:
            return Response(
                error_payload("not_found", "Document not found."),
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "id": str(document.id),
                "library_id": str(document.library_id),
                "filename": document.filename,
                "mime": document.mime,
                "size_bytes": document.size_bytes,
                "status": document.status,
                "error": document.error,
                "page_count": document.page_count,
                "ingest_cursor": document.ingest_cursor,
                "embed_model": document.embed_model,
                "created_at": document.created_at.isoformat(),
            }
        )


class LibraryDocumentListView(APIView):
    """List a library's documents, so the UI can resume non-terminal ones."""

    def get(self, request, library_id):
        profile = getattr(request, "profile", None)
        if profile is None:  # pragma: no cover
            return Response(
                error_payload("unauthenticated", "No profile on the request."),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        library = Library.objects.filter(id=library_id, owner=profile).first()
        if library is None:
            return Response(
                error_payload("not_found", "Library not found."),
                status=status.HTTP_404_NOT_FOUND,
            )

        documents = Document.objects.filter(library=library).order_by("created_at")
        return Response(
            {
                "library": {
                    "id": str(library.id),
                    "title": library.title,
                    "document_count": documents.count(),
                    "max_documents": settings.MAX_DOCS_PER_LIBRARY,
                },
                "documents": [
                    {
                        "id": str(d.id),
                        "filename": d.filename,
                        "status": d.status,
                        "error": d.error,
                        "page_count": d.page_count,
                        "ingest_cursor": d.ingest_cursor,
                        "size_bytes": d.size_bytes,
                        "mime": d.mime,
                        "created_at": d.created_at.isoformat(),
                    }
                    for d in documents
                ],
            }
        )
