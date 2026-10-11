from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from pgvector.django import VectorField


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Profile(TimestampedModel):
    id = models.UUIDField(primary_key=True, editable=False)
    email = models.EmailField(null=True, blank=True)
    display_name = models.CharField(max_length=120, blank=True)

    max_documents = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "profiles"
        verbose_name = "profile"
        verbose_name_plural = "profiles"

    def __str__(self) -> str:
        return self.display_name or self.email or str(self.id)


class Library(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="libraries",
    )
    name = models.CharField(max_length=120)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "libraries"
        ordering = ["-is_default", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"],
                name="libraries_owner_name_uniq",
            ),
            models.UniqueConstraint(
                fields=["owner"],
                condition=models.Q(is_default=True),
                name="libraries_one_default_per_owner",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class DocumentStage(models.TextChoices):
    QUEUED = "queued", "Queued"
    PARSING = "parsing", "Parsing"
    CHUNKING = "chunking", "Chunking"
    EMBEDDING = "embedding", "Embedding"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"

TERMINAL_STAGES = frozenset({DocumentStage.READY, DocumentStage.FAILED})

STAGE_ORDER = (
    DocumentStage.QUEUED,
    DocumentStage.PARSING,
    DocumentStage.CHUNKING,
    DocumentStage.EMBEDDING,
    DocumentStage.READY,
)


class Document(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey(
        Library,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    owner = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="documents",
    )

    filename = models.CharField(max_length=255)
    storage_path = models.CharField(max_length=512, null=True, blank=True)
    content_type = models.CharField(max_length=128, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    page_count = models.PositiveIntegerField(null=True, blank=True)

    stage = models.CharField(
        max_length=16,
        choices=DocumentStage.choices,
        default=DocumentStage.QUEUED,
        db_index=True,
    )
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "documents"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "stage"], name="documents_owner_stage_idx"),
        ]

    def __str__(self) -> str:
        return self.filename

    @property
    def extension(self) -> str:
        return Path(self.filename).suffix.lower()


class MessageRole(models.TextChoices):
    USER = "user", "User"
    ASSISTANT = "assistant", "Assistant"


class ChatSession(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
    )
    library = models.ForeignKey(
        Library,
        on_delete=models.CASCADE,
        related_name="chat_sessions",
    )

    title = models.CharField(max_length=160, default="New chat")

    class Meta:
        db_table = "chat_sessions"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["owner", "-updated_at"], name="chat_sessions_owner_idx"),
        ]

    def __str__(self) -> str:
        return self.title


class ChatMessage(TimestampedModel):
    id = models.BigAutoField(primary_key=True)
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    role = models.CharField(max_length=16, choices=MessageRole.choices)
    content = models.TextField()

    citations = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "chat_messages"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["session", "created_at"], name="chat_messages_session_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.session_id}:{self.role}:{self.pk}"


class Chunk(TimestampedModel):
    id = models.BigAutoField(primary_key=True)
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    owner = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="chunks",
    )

    ordinal = models.PositiveIntegerField()
    page_number = models.PositiveIntegerField(null=True, blank=True)
    content = models.TextField()

    heading_path = models.TextField(blank=True, default="")

    embedding = VectorField(dimensions=settings.EMBEDDING_DIM, null=True, blank=True)

    token_count = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "chunks"
        ordering = ["document_id", "ordinal"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "ordinal"],
                name="chunks_document_ordinal_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["document"], name="chunks_document_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.document_id}:{self.ordinal}"
