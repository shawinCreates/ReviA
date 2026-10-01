"""The document schema, and the parts of it only a real Postgres can check.

Two things are asserted here that SQLite genuinely cannot verify: that the
`vector` extension is installed, and that the HNSW index over the embeddings
exists. Both are skipped rather than faked on SQLite, because a fake pass here
would be worse than no test.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import psycopg
import pytest
from django.db import IntegrityError, connection, transaction

from api.models import Chunk, Document, DocumentStage, Library, Profile

pytestmark = pytest.mark.django_db


def _owner() -> Profile:
    """A profile for a Supabase user.

    Ownership is a foreign key to Profile, not a bare uuid, so every owner in
    these tests has to exist. That mirrors the request path, where verifying a
    session creates the profile before anything else happens.
    """
    return Profile.objects.create(id=uuid.uuid4(), email=f"{uuid.uuid4().hex}@example.com")


def _library(owner: Profile, **kwargs) -> Library:
    defaults = {"owner": owner, "name": "My library"}
    return Library.objects.create(**{**defaults, **kwargs})


def _document(owner: Profile, library: Library, **kwargs) -> Document:
    defaults = {
        "owner": owner,
        "library": library,
        "filename": "paper.pdf",
        "storage_path": f"{owner.id}/paper.pdf",
    }
    return Document.objects.create(**{**defaults, **kwargs})


def _chunk(owner: Profile, document: Document, ordinal: int, **kwargs) -> Chunk:
    defaults = {"owner": owner, "document": document, "ordinal": ordinal, "content": "text"}
    return Chunk.objects.create(**{**defaults, **kwargs})


# --- what only Postgres can prove ------------------------------------------------


def test_vector_extension_is_installed():
    if connection.vendor != "postgresql":
        pytest.skip("the vector extension only exists on PostgreSQL")
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        assert cursor.fetchone() is not None


def test_hnsw_index_exists_over_chunk_embeddings():
    if connection.vendor != "postgresql":
        pytest.skip("HNSW is a PostgreSQL index method")
    with connection.cursor() as cursor:
        cursor.execute("SELECT indexdef FROM pg_indexes WHERE indexname = 'chunks_embedding_hnsw'")
        row = cursor.fetchone()
    assert row is not None, "the embedding index is missing"
    assert "hnsw" in row[0]
    assert "vector_cosine_ops" in row[0], "the index must match how retrieval scores similarity"


def test_embedding_round_trips_on_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("SQLite has no vector type")
    owner = _owner()
    document = _document(owner, _library(owner))
    vector = [0.5] * 384
    chunk = _chunk(owner, document, 1, embedding=vector)

    chunk.refresh_from_db()
    assert chunk.embedding == pytest.approx(vector, abs=1e-6)


def test_row_level_security_is_enabled_on_every_app_table():
    """The anon key ships in the frontend bundle, so PostgREST must be shut out.

    Supabase grants `anon` full access to every table in the public schema. RLS
    with no policies is what actually denies it, and this service is unaffected
    because it connects as the owner, which bypasses RLS.
    """
    if connection.vendor != "postgresql":
        pytest.skip("row level security is a PostgreSQL feature")
    tables = ["profiles", "libraries", "documents", "chunks"]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname, relrowsecurity FROM pg_class WHERE relname = ANY(%s)", [tables]
        )
        found = dict(cursor.fetchall())

    assert set(found) == set(tables), f"missing tables: {set(tables) - set(found)}"
    unprotected = sorted(name for name, enabled in found.items() if not enabled)
    assert unprotected == [], f"row level security is off on: {unprotected}"


@contextmanager
def _fresh_connection(*, autocommit: bool = True):
    """A connection that is not the test's.

    Two reasons. The test's own connection sits inside a transaction, and a
    permission error inside one poisons it: every later command fails until the
    block ends, taking the rest of the test with it. And a fresh connection is
    not the database owner, which is the entire point — RLS is bypassed for the
    owner, so checking it from the test's connection would prove nothing.

    Autocommit by default, because `ALTER TABLE` and `GRANT` cannot run inside a
    transaction that has pending trigger events, and a test cannot commit.
    """
    settings_dict = connection.settings_dict
    conn = psycopg.connect(
        host=settings_dict["HOST"],
        port=settings_dict["PORT"],
        user=settings_dict["USER"],
        password=settings_dict["PASSWORD"],
        dbname=settings_dict["NAME"],
        connect_timeout=10,
        autocommit=autocommit,
    )
    try:
        yield conn
    finally:
        conn.close()


#: Raised when this server cannot pose the question at all — no `anon` role, or
#: a test user that is not a member of it. Both are properties of the server
#: rather than of the code under test, so the caller skips.
_SKIPPABLE_ERRORS = (psycopg.ProgrammingError, psycopg.DatabaseError, psycopg.OperationalError)


def _skip_unless_anon_is_usable() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("row level security is a PostgreSQL feature")
    try:
        with _fresh_connection() as conn:
            conn.execute("SET ROLE anon")
            conn.execute("RESET ROLE")
    except _SKIPPABLE_ERRORS:
        pytest.skip("this server cannot step down to the anon role")


def _rows_visible_to_anon(table: str) -> int | None:
    """Count rows in `table` as the `anon` role, or None if that is not possible."""
    try:
        with _fresh_connection() as conn:
            conn.execute("SET ROLE anon")
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT count(*) FROM {table}")
                return cursor.fetchone()[0]
    except _SKIPPABLE_ERRORS:
        return None


def _set_row_level_security(table: str, *, enabled: bool) -> None:
    verb = "ENABLE" if enabled else "DISABLE"
    with _fresh_connection() as conn:
        conn.execute(f"ALTER TABLE {table} {verb} ROW LEVEL SECURITY")


def _seed_one_document() -> None:
    """Insert a document the `anon` role would be able to see, if RLS allowed it."""
    owner = _owner()
    document = _document(owner, _library(owner))
    with _fresh_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO documents (id, owner_id, library_id, filename, stage,"
            " size_bytes, content_type, error_message, created_at, updated_at)"
            " VALUES (%s, %s, %s, %s, %s, 0, '', '', now(), now())",
            (
                document.id,
                owner.id,
                document.library_id,
                document.filename,
                document.stage,
            ),
        )


def test_the_anon_role_cannot_read_documents():
    """Proves the deny is effective, not just that the flag is set.

    The owner bypasses RLS, so checking the flag alone would prove nothing about
    what PostgREST can actually reach. The GRANT matters too: Supabase grants
    `anon` SELECT on every public table, so the refusal has to come from RLS
    rather than from a missing privilege.
    """
    _skip_unless_anon_is_usable()

    _seed_one_document()
    with _fresh_connection() as conn:
        conn.execute("GRANT SELECT ON documents TO anon")

    assert _rows_visible_to_anon("documents") == 0, "anon can read documents despite RLS"


def test_anon_would_see_the_rows_without_row_level_security():
    """The control: the same read, with RLS off, does return the row.

    Without this, "anon read nothing" could just mean the grant never took, or
    that the table is empty for some unrelated reason. Turning RLS off as the
    owner is the only way to show the deny is doing the work.
    """
    _skip_unless_anon_is_usable()

    _seed_one_document()
    with _fresh_connection() as conn:
        conn.execute("GRANT SELECT ON documents TO anon")
    _set_row_level_security("documents", enabled=False)
    try:
        assert _rows_visible_to_anon("documents") == 1
    finally:
        _set_row_level_security("documents", enabled=True)


# --- structural guarantees ------------------------------------------------------


def test_a_document_belongs_to_a_library_and_an_owner():
    owner = _owner()
    library = _library(owner)
    document = _document(owner, library)

    assert document.library_id == library.id
    assert document.owner_id == owner.id
    assert document.stage == DocumentStage.QUEUED


def test_deleting_a_document_removes_its_chunks():
    owner = _owner()
    document = _document(owner, _library(owner))
    _chunk(owner, document, 1)
    _chunk(owner, document, 2)

    document.delete()

    assert Chunk.objects.filter(document_id=document.id).count() == 0


def test_chunk_ordinals_are_unique_within_a_document():
    owner = _owner()
    document = _document(owner, _library(owner))
    _chunk(owner, document, 1)

    with pytest.raises(IntegrityError), transaction.atomic():
        _chunk(owner, document, 1)


def test_only_one_default_library_per_owner():
    owner = _owner()
    _library(owner, is_default=True)

    with pytest.raises(IntegrityError), transaction.atomic():
        _library(owner, is_default=True)


def test_two_owners_can_each_have_a_default_library():
    first, second = _owner(), _owner()
    _library(first, is_default=True)
    _library(second, is_default=True)

    assert Library.objects.filter(is_default=True).count() == 2


def test_extension_is_derived_from_the_filename():
    owner = _owner()
    library = _library(owner)

    assert _document(owner, library, filename="a.PDF").extension == ".pdf"
    assert _document(owner, library, filename="notes.md").extension == ".md"
    assert _document(owner, library, filename="README").extension == ""
