"""
Library endpoints.

A document belongs to a library, and a library belongs to one owner, so these
are the entry point to the whole upload flow: there is nothing to upload into
until a library exists. They are small, but they are what makes the frontend's
first screen possible without hand-seeding a row in the database.
"""

from __future__ import annotations

from django.db.models import Count, Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .errors import error_payload
from .models import Document, Library

# Long enough for a real title, short enough that it stays a label rather than a
# paragraph. Enforced here rather than in the UI, per quotas.md.
MAX_TITLE_LENGTH = 200


def _library_dict(library: Library) -> dict:
    counts = library.documents.aggregate(
        document_count=Count("id"),
        ready_count=Count("id", filter=Q(status=Document.STATUS_READY)),
    )
    return {
        "id": str(library.id),
        "title": library.title,
        "created_at": library.created_at.isoformat(),
        "document_count": counts["document_count"],
        "ready_count": counts["ready_count"],
    }


class LibraryListCreateView(APIView):
    """
    `GET /api/libraries` lists the caller's libraries; `POST` creates one.

    Scoped to `owner=profile` on both verbs. A library id is a UUID, but that is
    not authorization: the filter is.
    """

    def get(self, request):
        profile = getattr(request, "profile", None)
        if profile is None:  # pragma: no cover - middleware guarantees this
            return Response(
                error_payload("unauthenticated", "No profile on the request."),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        libraries = (
            Library.objects.filter(owner=profile)
            .annotate(
                document_count=Count("documents"),
                ready_count=Count(
                    "documents", filter=Q(documents__status=Document.STATUS_READY)
                ),
            )
            .order_by("created_at")
        )
        return Response(
            [
                {
                    "id": str(library.id),
                    "title": library.title,
                    "created_at": library.created_at.isoformat(),
                    "document_count": library.document_count,
                    "ready_count": library.ready_count,
                }
                for library in libraries
            ]
        )

    def post(self, request):
        profile = getattr(request, "profile", None)
        if profile is None:  # pragma: no cover - middleware guarantees this
            return Response(
                error_payload("unauthenticated", "No profile on the request."),
                status=status.HTTP_401_UNAUTHORIZED,
            )

        body = request.data or {}
        title = str(body.get("title", "")).strip()

        if not title:
            return Response(
                error_payload("bad_request", "A library needs a title."),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(title) > MAX_TITLE_LENGTH:
            return Response(
                error_payload(
                    "bad_request",
                    f"Titles are at most {MAX_TITLE_LENGTH} characters.",
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        library = Library.objects.create(owner=profile, title=title)
        return Response(_library_dict(library), status=status.HTTP_201_CREATED)


class LibraryDetailView(APIView):
    """
    `GET /api/libraries/:id` returns one library with its document list.

    The document list is the same shape as `GET /api/libraries/:id/documents`,
    so the frontend has one parser for both.
    """

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

        documents = library.documents.order_by("created_at")
        payload = _library_dict(library)
        payload["documents"] = [
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
        ]
        return Response(payload)
