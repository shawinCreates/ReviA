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
    return Response(
        {"error": {"code": code, "message": message}},
        status=status_code,
    )


class HealthView(APIView):
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
    def get(self, request: Request) -> Response:
        principal: SupabasePrincipal = request.user

        library_id = request.query_params.get("library")
        queryset = access.documents_for(principal)

        if library_id:
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
    throttle_scope = "upload"

    def post(self, request: Request) -> Response:
        principal: SupabasePrincipal = request.user

        upload = request.FILES.get("file")
        if upload is None:
            return _error("no_file", "No file was included in the request.")

        try:
            validated = uploads.validate_upload(upload)
        except uploads.UploadRejected as exc:
            return _error(exc.code, exc.reason, status.HTTP_422_UNPROCESSABLE_ENTITY)

        exceeded = _quota_exceeded(principal)
        if exceeded is not None:
            return _error("quota_exceeded", exceeded, status.HTTP_409_CONFLICT)

        library = _resolve_library(principal, request.data.get("library"))
        if isinstance(library, Response):
            return library

        try:
            stored = storage.upload_file(principal.id, validated.filename, upload)
        except storage.StorageNotConfiguredError as exc:
            logger.error("Storage is not configured: %s", exc)
            return _error(
                "storage_unavailable",
                "File storage is not configured on this server.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except storage.StorageError:
            return _error(
                "storage_failed",
                "The file could not be stored.",
                status.HTTP_502_BAD_GATEWAY,
            )

        try:
            document = library_service.create_document(
                principal,
                library,
                filename=validated.filename,
                content_type=validated.content_type,
                size_bytes=stored.size,
                storage_path=stored.path,
            )
        except Exception:
            try:
                storage.delete_file(stored.path)
            except storage.StorageError:
                logger.exception("Could not remove orphaned upload %s", stored.path)
            raise

        return Response(
            {"document": DocumentSerializer(document).data},
            status=status.HTTP_201_CREATED,
        )


class DocumentDetailView(APIView):
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

        # Row first: a storage failure must not leave a visible document pointing at nothing.
        document.delete()

        if storage_path:
            try:
                storage.delete_file(storage_path)
            except storage.StorageError as exc:
                logger.warning(
                    "Deleted document but could not remove %s from storage: %s",
                    storage_path,
                    exc,
                )

        return Response(status=status.HTTP_204_NO_CONTENT)


def _resolve_library(principal: SupabasePrincipal, library_id) -> Library | Response:
    if not library_id:
        return library_service.get_or_create_default_library(principal)

    library = access.libraries_for(principal).filter(pk=library_id).first()
    if library is None:
        return _error("not_found", "No such library.", status.HTTP_404_NOT_FOUND)
    return library


def _quota_exceeded(principal: SupabasePrincipal) -> str | None:
    profile = access.profile_for(principal)
    if profile is None:
        return None

    limit = profile.max_documents
    if limit <= 0:
        # 0 means unlimited, not merely unconfigured.
        return None

    used = access.documents_for(principal).count()
    if used < limit:
        return None

    return f"Your library holds {used} of {limit} documents. Remove one to upload another."


class AskView(APIView):
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
            answer, _ = chat.answer_question(
                principal, session=session, question=question
            )
        except chat.AnswerError as exc:
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
                "citations": answer.citations,
                "retrieved": answer.retrieved,
                "used_context": answer.used_context,
            },
            status=status.HTTP_201_CREATED,
        )


class ChatSessionListView(APIView):
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
    for errors in serializer.errors.values():
        if isinstance(errors, list) and errors:
            return str(errors[0])
        return str(errors)
    return "The request was not valid."
