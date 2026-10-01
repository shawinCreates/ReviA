"""Application data models.

Identity lives in `supabase.auth.users`. `Profile` is a local mirror keyed by
that id: it exists so the rest of the app has a row to hang application state
off (display name, quota) without re-implementing authentication. The id is the
Supabase user id, so there is never a mapping to keep in sync.

## On access control

Two different mechanisms, doing two different jobs. Confusing them is how a
Supabase project ends up with policies that look like protection and enforce
nothing.

**RLS, for everyone else.** Supabase grants `anon` and `authenticated` full
access to every table in the public schema, and PostgREST will serve any of them
to a request carrying the anon key — which ships in the frontend bundle.
Migration `0003` enables RLS on the tables below with no policies, which denies
those roles outright. So nothing in this schema is reachable except through this
service.

**Ownership, for the one account against another.** This service connects as the
database owner, and the owner bypasses RLS by design. So RLS cannot enforce
ownership *here*, and a policy that tried would be inert. Ownership is enforced
in the query layer instead: every read and write goes through `api.access`, which
scopes a queryset to the authenticated user, and a missing scope is a bug that
`test_access.py` exists to surface.

RLS keeps other people out of Postgres entirely. `api.access` keeps one account
out of another's rows within this service. Neither substitutes for the other.
"""

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
    """One row per Supabase user, created on first authenticated request."""

    id = models.UUIDField(primary_key=True, editable=False)
    email = models.EmailField(null=True, blank=True)
    display_name = models.CharField(max_length=120, blank=True)

    # Per-user allowance on stored documents. A value of 0 means "unlimited",
    # which is the right default for local development and the wrong one for
    # production, so it is explicit rather than implied by a null.
    max_documents = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "profiles"
        verbose_name = "profile"
        verbose_name_plural = "profiles"

    def __str__(self) -> str:
        return self.display_name or self.email or str(self.id)


class Library(TimestampedModel):
    """A named collection of documents belonging to one user.

    Every user gets a default library on first sign-in, because the alternative
    is a chat session with nowhere to read from, which reads as a bug in the
    product rather than a missing feature.
    """

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
            # Library names are unique per owner, not globally, so two people
            # can each have a "Lecture notes" library.
            models.UniqueConstraint(
                fields=["owner", "name"],
                name="libraries_owner_name_uniq",
            ),
            # At most one default library per owner. A partial unique index
            # enforces this without forcing a name to be unique.
            models.UniqueConstraint(
                fields=["owner"],
                condition=models.Q(is_default=True),
                name="libraries_one_default_per_owner",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class DocumentStage(models.TextChoices):
    """Where a document is in the ingestion pipeline.

    These values are the contract with the frontend's `STAGES` in
    `frontend/lib/config.ts`. Changing one means changing both, or the pipeline
    board renders a stage it has no name for.
    """

    QUEUED = "queued", "Queued"
    PARSING = "parsing", "Parsing"
    CHUNKING = "chunking", "Chunking"
    EMBEDDING = "embedding", "Embedding"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"


#: Stages a document can no longer leave. Used to reject an out-of-order
#: transition, which would otherwise let a retry move a failed document back
#: to ready while its chunks are still missing.
TERMINAL_STAGES = frozenset({DocumentStage.READY, DocumentStage.FAILED})

#: The order a document moves through, used to reject backwards transitions.
STAGE_ORDER = (
    DocumentStage.QUEUED,
    DocumentStage.PARSING,
    DocumentStage.CHUNKING,
    DocumentStage.EMBEDDING,
    DocumentStage.READY,
)


class Document(TimestampedModel):
    """An uploaded file and its state in the ingestion pipeline."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey(
        Library,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    # Denormalised from library.owner so a document can be scoped without a
    # join on every query. Kept honest by the service layer, which always
    # derives it from the library rather than accepting it from a client.
    # A foreign key to Profile rather than a bare uuid: the profile is created
    # when a session is first verified, so it always exists by the time a
    # document is created, and it gives account deletion a cascade to rely on.
    owner = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="documents",
    )

    filename = models.CharField(max_length=255)
    # Path within the storage bucket. Null until the upload completes, so a
    # half-finished upload is not mistaken for a readable file.
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
    # Why the pipeline gave up. Only meaningful while stage is FAILED, but
    # stored as-is because the message is what a user needs to see.
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "documents"
        ordering = ["-created_at"]
        indexes = [
            # The pipeline board reads one owner's documents in stage order.
            models.Index(fields=["owner", "stage"], name="documents_owner_stage_idx"),
        ]

    def __str__(self) -> str:
        return self.filename

    @property
    def extension(self) -> str:
        # `Path.suffix` rather than `rpartition(".")`, which returns the whole
        # filename as the suffix when there is no dot, turning "README" into
        # ".readme". It also leaves dotfiles like ".gitignore" extensionless.
        return Path(self.filename).suffix.lower()


class MessageRole(models.TextChoices):
    """Who wrote a message in a conversation.

    A closed set rather than a free string: the prompt builder switches on it to
    decide how much of the transcript to include and with which prefix, and a
    typo in a role would silently drop history from the context.
    """

    USER = "user", "User"
    ASSISTANT = "assistant", "Assistant"


class ChatSession(TimestampedModel):
    """One conversation against one library.

    Scoped to a library rather than to a user alone, because the answer depends
    entirely on which documents were searched. A session that outlived a change
    of library would show history whose citations came from documents the user
    is no longer looking at, with no way to tell that from the transcript.
    """

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

    # A generated title, edited by the user if they want. Kept short and
    # overwritten on every save, because a chat list is only navigable if each
    # row is identifiable without opening it.
    title = models.CharField(max_length=160, default="New chat")

    class Meta:
        db_table = "chat_sessions"
        # Newest first, which is how a sidebar is read.
        ordering = ["-updated_at"]
        indexes = [
            # The sidebar lists one owner's sessions; nothing else reads them
            # in bulk.
            models.Index(fields=["owner", "-updated_at"], name="chat_sessions_owner_idx"),
        ]

    def __str__(self) -> str:
        return self.title


class ChatMessage(TimestampedModel):
    """One turn in a conversation.

    Citations are stored on the assistant's own rows as JSON rather than as a
    relation to `Chunk`. A citation is a snapshot of what was shown at the time
    of the answer: the document it came from, the page, and the text that was
    quoted. Storing the reference alone would mean a later re-ingestion, or a
    deletion, silently rewriting the history of what the product claimed.
    """

    id = models.BigAutoField(primary_key=True)
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    role = models.CharField(max_length=16, choices=MessageRole.choices)
    content = models.TextField()

    # Only set on assistant messages. `default=list` rather than a module-level
    # callable so the schema keeps a JSONB default of [].
    citations = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "chat_messages"
        # Read back in order to build the prompt, which is the only way this
        # table is ever queried.
        ordering = ["created_at", "id"]
        indexes = [
            # Turns are always fetched for one session, in order.
            models.Index(fields=["session", "created_at"], name="chat_messages_session_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.session_id}:{self.role}:{self.pk}"


class Chunk(TimestampedModel):
    """One retrievable span of a document, with its embedding.

    `ordinal` is the position within the document and `page_number` the page it
    came from. Both exist because an answer has to cite a page: `ordinal` orders
    chunks back into readable context, `page_number` is what gets shown.
    """

    id = models.BigAutoField(primary_key=True)
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    # Denormalised from document.owner, for the same reason document.owner is.
    owner = models.ForeignKey(
        Profile,
        on_delete=models.CASCADE,
        related_name="chunks",
    )

    ordinal = models.PositiveIntegerField()
    page_number = models.PositiveIntegerField(null=True, blank=True)
    content = models.TextField()

    # Width comes from configuration because the embedding model is configurable,
    # and vectors from two models are not comparable even at the same dimension.
    # The migration bakes in the current value; see test_models.py for the guard
    # against the two drifting apart.
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
            # Similarity search always filters to a set of documents first, so
            # the index leads with the foreign key.
            models.Index(fields=["document"], name="chunks_document_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.document_id}:{self.ordinal}"
