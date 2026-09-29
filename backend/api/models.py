"""
Data model for the EndNote API.

Mirrors data-model.md. Three things are deliberate and load-bearing:

- `Profile.id` is the Supabase auth user id from the JWT `sub` claim. There is
  no separate local identity, because Supabase owns auth (decisions.md D-004).
- `Chunk.library_id` is denormalised from `Document`. It is set on write, so
  it cannot drift, and it lets retrieval filter without joining through
  `document`.
- `Document.ingest_cursor` lives in the database, not in process memory, so a
  Render cold start or a deploy mid-ingest cannot lose progress. See
  ingestion.md and decisions.md D-006.
"""

import uuid

from django.conf import settings
from django.db import models
from pgvector.django import HnswIndex, VectorField

# One source of truth. This was a hardcoded 1024 for the planned Cloudflare
# bge-m3; the local ONNX model is 384-dim. Reading it from settings means a
# model change and a migration cannot drift apart silently.
EMBEDDING_DIM = settings.EMBEDDING_DIM


class Profile(models.Model):
    """Mirror of a Supabase auth user, created lazily on first request."""

    id = models.UUIDField(primary_key=True, editable=False)
    email = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "profile"

    def __str__(self) -> str:
        return self.email


class Library(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="libraries", db_column="owner_id"
    )
    title = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "library"
        indexes = [models.Index(fields=["owner"], name="library_owner_idx")]

    def __str__(self) -> str:
        return self.title


class Document(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_PARSING = "parsing"
    STATUS_INDEXING = "indexing"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_PARSING, "Parsing"),
        (STATUS_INDEXING, "Indexing"),
        (STATUS_READY, "Ready"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey(
        Library, on_delete=models.CASCADE, related_name="documents", db_column="library_id"
    )
    filename = models.TextField()
    storage_path = models.TextField()
    mime = models.TextField()
    size_bytes = models.BigIntegerField()
    page_count = models.IntegerField(null=True, blank=True)
    status = models.TextField(choices=STATUS_CHOICES, default=STATUS_QUEUED)
    error = models.TextField(null=True, blank=True)
    # The resume point. Survives cold starts and deploys because it is a row,
    # not a local variable. See ingestion.md.
    ingest_cursor = models.IntegerField(default=0)
    embed_model = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "document"
        indexes = [models.Index(fields=["library"], name="document_library_idx")]

    def __str__(self) -> str:
        return self.filename


class Page(models.Model):
    """The citation unit. One row per page; a citation resolves to exactly one."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="pages", db_column="document_id"
    )
    page_number = models.IntegerField()
    text = models.TextField()
    char_len = models.IntegerField()
    heading_path = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "page"
        # Uniqueness is what makes re-ingesting a page range idempotent: a retry
        # upserts the same row instead of appending a duplicate. See
        # ingestion.md.
        constraints = [
            models.UniqueConstraint(
                fields=["document", "page_number"], name="page_document_pagenum_uniq"
            )
        ]
        indexes = [
            models.Index(fields=["document", "page_number"], name="page_document_idx")
        ]

    def __str__(self) -> str:
        return f"{self.document_id} p{self.page_number}"


class Chunk(models.Model):
    """
    A slice of one page. Never spans pages, which is what makes a citation
    unambiguous by construction. See retrieval.md.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="chunks", db_column="document_id"
    )
    page = models.ForeignKey(
        Page, on_delete=models.CASCADE, related_name="chunks", db_column="page_id"
    )
    # Denormalised on write so it cannot drift, and so retrieval filters in one
    # place. See data-model.md.
    library = models.ForeignKey(
        Library, on_delete=models.CASCADE, related_name="chunks", db_column="library_id"
    )
    page_number = models.IntegerField()
    ordinal = models.IntegerField()
    text = models.TextField()
    heading_path = models.TextField(null=True, blank=True)
    token_count = models.IntegerField()
    # Dimension comes from settings so a model change and the schema cannot
    # drift apart silently. bge-m3 was 1024; the local ONNX model is 384.
    embedding = VectorField(dimensions=EMBEDDING_DIM)
    # Populated at write time so the lexical leg never has to re-parse text.
    # A real tsvector with a GIN index, added in a later migration, because
    # generating tsvector is database-specific. See phases/phase-2-retrieval.md.
    tsv = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chunk"
        # Without this, a retried ingest appends a second copy of every chunk
        # for the page range it reprocesses, and the HNSW index silently
        # returns near-duplicate results. This is what makes step 10 of
        # ingestion.md an upsert rather than an append. See ingestion.md.
        constraints = [
            models.UniqueConstraint(
                fields=["page", "ordinal"], name="chunk_page_ordinal_uniq"
            )
        ]
        indexes = [
            models.Index(fields=["library"], name="chunk_library_idx"),
            # vector_cosine_ops must match the <=> operator used at query time.
            # A mismatch between the two is silent and expensive to debug, so
            # the operator class is pinned here rather than left to default.
            HnswIndex(
                name="chunk_embedding_hnsw",
                fields=["embedding"],
                opclasses=["vector_cosine_ops"],
                m=16,
                ef_construction=64,
            ),
        ]


class ChatSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey(
        Library, on_delete=models.CASCADE, related_name="sessions", db_column="library_id"
    )
    user = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="sessions", db_column="user_id"
    )
    title = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_session"
        indexes = [
            models.Index(fields=["user", "-created_at"], name="chat_session_user_idx")
        ]


class Message(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_CHOICES = [(ROLE_USER, "User"), (ROLE_ASSISTANT, "Assistant")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name="messages", db_column="session_id"
    )
    role = models.TextField(choices=ROLE_CHOICES)
    content = models.TextField()
    # [{"marker": 1, "document_id", "page_number", "chunk_id", "snippet"}]
    citations = models.JSONField(default=list)
    # Tracked so over- and under-refusal are both reviewable by hand. A
    # refusal is correct behaviour, not a failure. See risks.md R-5.
    refused = models.BooleanField(default=False)
    model = models.TextField(null=True, blank=True)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    latency_ms = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "message"
        indexes = [models.Index(fields=["session", "created_at"], name="message_session_idx")]


class UsageLedger(models.Model):
    """
    Per-user daily counters. Failures are counted too, or a client that times
    out and retries becomes an unlimited-budget path. See quotas.md.
    """

    user = models.ForeignKey(
        Profile, on_delete=models.CASCADE, related_name="usage", db_column="user_id"
    )
    # UTC day, always. Mixing UTC and local days makes the reset ambiguous.
    day = models.DateField()
    requests = models.IntegerField(default=0)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    rerank_calls = models.IntegerField(default=0)

    class Meta:
        db_table = "usage_ledger"
        constraints = [
            models.UniqueConstraint(fields=["user", "day"], name="usage_ledger_user_day_uniq")
        ]


class PlatformLedger(models.Model):
    """
    The second quota layer. A per-user cap alone does not stop many users from
    collectively exhausting the org-wide Groq limit. See quotas.md.
    """

    day = models.DateField(primary_key=True)
    requests = models.IntegerField(default=0)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    rerank_calls = models.IntegerField(default=0)

    class Meta:
        db_table = "platform_ledger"


class RetrievalLog(models.Model):
    """
    How retrieval quality is measured without paying for an eval tool. The
    ordered chunk_ids are recall@k against the golden set. See retrieval.md.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    query = models.TextField()
    library = models.ForeignKey(
        Library, on_delete=models.CASCADE, related_name="retrieval_logs", db_column="library_id"
    )
    # SET NULL: a log must survive its message being deleted.
    message = models.ForeignKey(
        Message,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retrieval_logs",
        db_column="message_id",
    )
    chunk_ids = models.JSONField(default=list)
    scores = models.JSONField(default=list)
    dense_hits = models.IntegerField(default=0)
    lexical_hits = models.IntegerField(default=0)
    reranked = models.BooleanField(default=False)
    model = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "retrieval_log"
