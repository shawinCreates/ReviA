"""API views.

Scope so far is deliberately thin: a health probe that does not touch the
database, and `/me` which proves the cookie-to-Profile path end to end. The
library, upload and chat endpoints build on these once they exist.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import connection
from django.db.models import Count
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api import access, chat, library_service, storage, uploads
from api.auth import SupabasePrincipal
from api.models import Document, DocumentStage, Library
from api.profiles import get_or_create_profile
from api.serializers import (
    AskQuestionSerializer,
    ChatMessageSerializer,
    ChatSessionSerializer,
    DocumentSerializer,
    LibrarySerializer,
    ProfileSerializer,
)

logger = logging.getLogger(__name__)


def _error(code: str, message: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> Response:
    """A consistent error shape, so the frontend has one thing to parse."""
    return Response(
        {"error": {"code": code, "message": message}},
        status=status_code,
    )


class HealthView(APIView):
    """Liveness and readiness in one probe.

    Reports database reachability separately from serving status: an API that
    cannot reach Postgres is running but not ready, and conflating the two makes
    a bad deploy look like a crash.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request: Request) -> Response:
        database_ok = True
        database_error: str | None = None

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as exc:
            database_ok = False
            database_error = type(exc).__name__
            logger.warning("Health check could not reach the database: %s", exc)

        body = {
            "status": "ok" if database_ok else "degraded",
            "database": "ok" if database_ok else "unreachable",
        }
        if database_error:
            body["database_error"] = database_error

        if database_ok:
            pipeline = _pipeline_summary()
            if pipeline is not None:
                body["pipeline"] = pipeline

        return Response(body, status=status.HTTP_200_OK)


def _pipeline_summary() -> dict | None:
    """Per-stage document counts, or None where they are not reported.

    The reason this matters: an upload only creates a queued row, so a worker
    that is not running leaves documents at "queued" indefinitely while the API
    still reports itself healthy. Every other signal here says the process is
    fine; only the queue size says whether ingestion is actually happening.

    DEBUG-gated because this view is unauthenticated, and document counts are
    not something to publish to whoever asks. The production answer to "is
    ingestion working" is a metric on the queue depth, not a public endpoint.
    """
    if not settings.DEBUG:
        return None

    try:
        counts = {
            row["stage"]: row["total"]
            for row in Document.objects.values("stage").annotate(total=Count("id"))
        }
    except Exception as exc:
        logger.warning("Could not summarise the ingestion pipeline: %s", exc)
        return None

    stages = {stage.value: counts.get(stage.value, 0) for stage in DocumentStage}
    return {
        "stages": stages,
        "queued": stages[DocumentStage.QUEUED.value],
        # Anything mid-pipeline, i.e. claimed but not finished. Non-zero with
        # nothing moving is the signature of a stalled document.
        "in_progress": sum(
            stages[stage.value]
            for stage in (
                DocumentStage.PARSING,
                DocumentStage.CHUNKING,
                DocumentStage.EMBEDDING,
            )
        ),
    }


class MeView(APIView):
    """The caller's own profile.

    Doubles as the end-to-end check that cookie parsing, token verification and
    profile provisioning all work against the real Supabase project.
    """

    def get(self, request: Request) -> Response:
        principal: SupabasePrincipal = request.user
        profile = get_or_create_profile(principal)

        return Response(
            {
                "user": {
                    "id": str(principal.id),
                    "email": principal.email,
                },
                "profile": ProfileSerializer(profile).data,
            }
        )


class DemoPrincipalView(APIView):
    """Confirms whether the caller is signed in, without requiring it.

    The frontend needs to know which of two states to render, and a 403 is a
    clumsy way to say "signed out". This is that signal.
    """

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        user = request.user
        authenticated = bool(user and getattr(user, "is_authenticated", False))
        return Response(
            {
                "authenticated": authenticated,
                "user_id": str(user.id) if authenticated else None,
            }
        )


class LibraryListView(APIView):
    """The caller's libraries, with their default one guaranteed to exist.

    Creating the default here rather than at sign-up means a user who signed up
    before this table existed, or whose first request failed, recovers on their
    next request instead of having no library to upload into.
    """

    def get(self, request: Request) -> Response:
        principal: SupabasePrincipal = request.user
        library_service.get_or_create_default_library(principal)

        libraries = (
            access.libraries_for(principal)
            .annotate(document_count=Count("documents"))
            .order_by("-is_default", "created_at")
        )
        return Response({"libraries": LibrarySerializer(libraries, many=True).data})


class DocumentListView(APIView):
    """Documents in one library, for the library column and the pipeline board."""

    def get(self, request: Request) -> Response:
        principal: SupabasePrincipal = request.user

        library_id = request.query_params.get("library")
        queryset = access.documents_for(principal)

        if library_id:
            # Scoping the document query by owner first, then checking the
            # library belongs to them, means a foreign library_id returns 404
            # rather than leaking whether that library exists.
            library = access.libraries_for(principal).filter(pk=library_id).first()
            if library is None:
                return _error("not_found", "No such library.", status.HTTP_404_NOT_FOUND)
            queryset = queryset.filter(library=library)

        documents = queryset.annotate(chunk_count=Count("chunks")).order_by("-created_at")

        payload = {
            "documents": DocumentSerializer(documents, many=True).data,
            "stage_counts": library_service.document_counts_by_stage(documents),
        }
        return Response(payload)


class UploadDocumentView(APIView):
    """Accept a file, store it, and register it as a queued document.

    The row is created before the upload is stored, so the document exists even
    if storing the bytes fails — otherwise a failed upload would leave the user
    with nothing on the board and no explanation. `fail_document` records why,
    and that is what the pipeline column shows.
    """

    throttle_scope = "upload"

    def post(self, request: Request) -> Response:
        principal: SupabasePrincipal = request.user

        upload = request.FILES.get("file")
        if upload is None:
            return _error("no_file", "No file was included in the request.")

        try:
            validated = uploads.validate_upload(upload)
        except uploads.UploadRejected as exc:
            # 422: the request was well-formed and understood, but its contents
            # cannot be processed. A 400 would suggest the shape was wrong.
            return _error(exc.code, exc.reason, status.HTTP_422_UNPROCESSABLE_ENTITY)

        exceeded = _quota_exceeded(principal)
        if exceeded is not None:
            return _error("quota_exceeded", exceeded, status.HTTP_409_CONFLICT)

        library = _resolve_library(principal, request.data.get("library"))
        if isinstance(library, Response):
            return library

        document = library_service.create_document(
            principal,
            library,
            filename=validated.filename,
            content_type=validated.content_type,
            size_bytes=validated.size,
        )

        try:
            stored = storage.upload_file(principal.id, validated.filename, upload)
        except storage.StorageNotConfiguredError as exc:
            logger.error("Storage is not configured: %s", exc)
            library_service.fail_document(document, str(exc))
            return _error(
                "storage_unavailable",
                "File storage is not configured on this server.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except storage.StorageError as exc:
            library_service.fail_document(document, str(exc))
            return _error(
                "storage_failed",
                "The file could not be stored.",
                status.HTTP_502_BAD_GATEWAY,
            )

        # Recorded only once the bytes are known to be in the bucket, so a reader
        # never follows a storage path that has nothing behind it.
        document.storage_path = stored.path
        document.size_bytes = stored.size
        document.save(update_fields=["storage_path", "size_bytes", "updated_at"])

        return Response(
            {"document": DocumentSerializer(document).data},
            status=status.HTTP_201_CREATED,
        )


class DocumentDetailView(APIView):
    """One document, and deleting it.

    Delete removes the stored file as well as the row, and treats a missing file
    as success. Retrying a delete is normal, and failing the second time would
    leave the row gone and the object orphaned with nothing left to clean it up.
    """

    throttle_scope = "session"

    def get(self, request: Request, document_id) -> Response:
        document = access.documents_for(request.user).filter(pk=document_id).first()
        if document is None:
            return _error("not_found", "No such document.", status.HTTP_404_NOT_FOUND)

        return Response({"document": DocumentSerializer(document).data})

    def delete(self, request: Request, document_id) -> Response:
        principal: SupabasePrincipal = request.user
        document = access.documents_for(principal).filter(pk=document_id).first()
        if document is None:
            return _error("not_found", "No such document.", status.HTTP_404_NOT_FOUND)

        storage_path = document.storage_path

        # The row first, so a storage failure cannot leave a visible document
        # pointing at nothing. Chunks cascade away with it.
        document.delete()

        if storage_path:
            try:
                storage.delete_file(storage_path)
            except storage.StorageError as exc:
                # The user-visible outcome is already correct. This is a cleanup
                # problem for an operator, not a failure to report to the caller.
                logger.warning(
                    "Deleted document but could not remove %s from storage: %s",
                    storage_path,
                    exc,
                )

        return Response(status=status.HTTP_204_NO_CONTENT)


def _resolve_library(principal: SupabasePrincipal, library_id) -> Library | Response:
    """The library to upload into, defaulting to the caller's default one.

    A library belonging to somebody else is a 404, matching `DocumentListView`:
    a 403 would confirm that it exists.
    """
    if not library_id:
        return library_service.get_or_create_default_library(principal)

    library = access.libraries_for(principal).filter(pk=library_id).first()
    if library is None:
        return _error("not_found", "No such library.", status.HTTP_404_NOT_FOUND)
    return library


def _quota_exceeded(principal: SupabasePrincipal) -> str | None:
    """A message when the caller is over their allowance, else None."""
    profile = access.profile_for(principal)
    if profile is None:
        return None

    limit = profile.max_documents
    if limit <= 0:
        # 0 means unlimited, which is explicit rather than implied by a null so
        # that "no limit configured" and "no limit wanted" are the same thing.
        return None

    used = access.documents_for(principal).count()
    if used < limit:
        return None

    return f"Your library holds {used} of {limit} documents. Remove one to upload another."


class AskView(APIView):
    """Ask a question about a library, and get an answer with citations.

    The expensive endpoint: it embeds the question, searches, and generates. It
    has its own throttle scope for that reason, separate from ordinary reads.

    A session is created on the first question if the client did not name one, so
    a new chat needs no setup call. Continuing a chat means passing the session
    id back, which is what makes the history real rather than a client-side
    illusion.
    """

    throttle_scope = "generation"

    def post(self, request: Request) -> Response:
        principal: SupabasePrincipal = request.user

        serializer = AskQuestionSerializer(data=request.data)
        if not serializer.is_valid():
            return _error("invalid_request", _first_error(serializer))

        question = serializer.validated_data["question"]
        session_id = serializer.validated_data.get("session")
        new_session = serializer.validated_data.get("new_session", False)

        library = _resolve_library(principal, serializer.validated_data.get("library"))
        if isinstance(library, Response):
            return library

        try:
            session = chat.open_session(
                principal,
                library=library,
                session_id=session_id,
                force_new=new_session,
            )
        except chat.AnswerError as exc:
            return _error(exc.code, exc.reason, status.HTTP_404_NOT_FOUND)

        try:
            # The retrieval result is not used here: the citations and the
            # retrieved list on the answer already carry what the client shows.
            answer, _ = chat.answer_question(
                principal, session=session, question=question
            )
        except chat.AnswerError as exc:
            # A rate limit or an outage is the caller's problem to retry, so 503
            # with the code saying so. A misconfiguration will not fix itself, so
            # 500 — a retry loop against a missing key never terminates.
            code = (
                status.HTTP_503_SERVICE_UNAVAILABLE
                if exc.retryable
                else status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            logger.warning("Answer failed (%s/%s): %s", exc.code, exc.retryable, exc.reason)
            return _error(exc.code, exc.reason, code)

        return Response(
            {
                "session": ChatSessionSerializer(session).data,
                "answer": answer.text,
                # Only the passages the answer actually cited. `retrieved` is the
                # full set considered, which the UI can show as "searched N
                # passages" so a thin answer is visibly thin.
                "citations": answer.citations,
                "retrieved": answer.retrieved,
                "used_context": answer.used_context,
            },
            status=status.HTTP_201_CREATED,
        )


class ChatSessionListView(APIView):
    """The caller's conversations, newest first."""

    def get(self, request: Request) -> Response:
        principal: SupabasePrincipal = request.user

        library = None
        library_id = request.query_params.get("library")
        if library_id:
            library = access.libraries_for(principal).filter(pk=library_id).first()
            if library is None:
                return _error("not_found", "No such library.", status.HTTP_404_NOT_FOUND)

        sessions = chat.list_sessions(principal, library=library)
        return Response({"sessions": ChatSessionSerializer(sessions, many=True).data})


class ChatSessionDetailView(APIView):
    """One conversation and its turns."""

    def get(self, request: Request, session_id) -> Response:
        principal: SupabasePrincipal = request.user

        session = access.chat_sessions_for(principal).filter(pk=session_id).first()
        if session is None:
            # 404, not 403: a 403 confirms the conversation exists.
            return _error("not_found", "No such conversation.", status.HTTP_404_NOT_FOUND)

        messages = chat.messages_for(principal, session)
        return Response(
            {
                "session": ChatSessionSerializer(session).data,
                "messages": ChatMessageSerializer(messages, many=True).data,
            }
        )


def _first_error(serializer) -> str:
    """The first validation message, in the same shape as every other error.

    DRF's own `detail` is a nested structure the frontend would have to walk.
    """
    for errors in serializer.errors.values():
        if isinstance(errors, list) and errors:
            return str(errors[0])
        return str(errors)
    return "The request was not valid."
