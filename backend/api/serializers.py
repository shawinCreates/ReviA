from __future__ import annotations

from django.conf import settings
from rest_framework import serializers

from api.models import ChatMessage, ChatSession, Chunk, Document, Library, Profile


class ProfileSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Profile
        fields = ["id", "email", "display_name", "max_documents", "created_at"]
        read_only_fields = fields


class LibrarySerializer(serializers.ModelSerializer):
    document_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Library
        fields = ["id", "name", "is_default", "document_count", "created_at"]
        read_only_fields = ["id", "owner", "is_default", "created_at", "document_count"]


class DocumentSerializer(serializers.ModelSerializer):
    stage_label = serializers.CharField(source="get_stage_display", read_only=True)
    extension = serializers.CharField(read_only=True)
    chunk_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Document
        fields = [
            "id",
            "filename",
            "extension",
            "stage",
            "stage_label",
            "storage_path",
            "content_type",
            "size_bytes",
            "page_count",
            "error_message",
            "chunk_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chunk
        fields = ["id", "document_id", "ordinal", "page_number", "content", "token_count"]
        read_only_fields = fields


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ["id", "role", "content", "citations", "created_at"]
        read_only_fields = fields


class ChatSessionSerializer(serializers.ModelSerializer):
    message_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = ChatSession
        fields = [
            "id",
            "library",
            "title",
            "message_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "owner", "message_count", "created_at", "updated_at"]


class AskQuestionSerializer(serializers.Serializer):
    question = serializers.CharField(
        allow_blank=False,
        trim_whitespace=True,
        max_length=settings.MAX_QUESTION_CHARS,
    )
    session = serializers.UUIDField(required=False, allow_null=True)
    library = serializers.UUIDField(required=False, allow_null=True)
    new_session = serializers.BooleanField(required=False, default=False)
