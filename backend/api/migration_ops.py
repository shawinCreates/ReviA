"""Custom migration operations.

Two things live here rather than in a migration file: raw SQL that has to be
conditional, and the reasoning behind it.

## Why these are conditional

The test suite runs on SQLite by default, and SQLite knows nothing about
`CREATE EXTENSION` or `USING hnsw`. Rather than pin the suite to Postgres, each
operation checks the backend and does nothing elsewhere. The `vector` column
still gets created there, because `vector` is only an opaque type name to
SQLite; the search index is simply absent, which costs nothing for tests that
do not exercise similarity search.

## Why they are not state operations

Both run SQL only. Neither creates or alters a Django model, so
`state_forwards` is deliberately a no-op: pretending they changed state would
make `makemigrations` believe the database had done something it has not.

These live outside the `migrations` package on purpose. Django loads every
module in `migrations/` as a migration candidate, so a helper module in there
raises `BadMigrationError` for having no `Migration` class.
"""

from __future__ import annotations

from django.db.migrations.operations.base import Operation


class PostgresOnlyOperation(Operation):
    """Base for raw SQL that applies only on PostgreSQL."""

    def state_forwards(self, app_label, state):
        """No state change: these operations only run SQL."""

    def is_postgres(self, schema_editor) -> bool:
        return schema_editor.connection.vendor == "postgresql"

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        raise NotImplementedError

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        raise NotImplementedError

    def allows_reference_model(self, operation, app_label, model_name):
        return False


class CreateVectorExtension(PostgresOnlyOperation):
    """Ensure pgvector is installed.

    `IF NOT EXISTS` because Supabase projects usually have it already, and
    creating an extension that exists is an error rather than a no-op.
    """

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if self.is_postgres(schema_editor):
            schema_editor.execute("CREATE EXTENSION IF NOT EXISTS vector")

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        # Deliberately left installed. Dropping a shared extension on rollback
        # can break anything else in the project that depends on it.
        return

    def describe(self):
        return "Create the pgvector extension if the backend is PostgreSQL"

    @property
    def migration_name_fragment(self):
        return "create_vector_extension"


class CreateHnswEmbeddingIndex(PostgresOnlyOperation):
    """Build an approximate nearest-neighbour index over chunk embeddings.

    HNSW rather than ivfflat: ivfflat needs a sensible `lists` value, which
    depends on how many rows exist, and choosing one before there is any data
    produces a poor index that has to be rebuilt later. HNSW does not need to
    know the row count.

    Cosine distance, matching the similarity the retrieval layer scores with.
    Vectors from two different embedding models are not comparable even at the
    same dimension, so this index is only valid for one EMBEDDING_DIM.
    """

    def __init__(self, name: str):
        self.name = name
        super().__init__()

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if self.is_postgres(schema_editor):
            schema_editor.execute(
                f"CREATE INDEX IF NOT EXISTS {self.name} ON chunks "
                "USING hnsw (embedding vector_cosine_ops)"
            )

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if self.is_postgres(schema_editor):
            schema_editor.execute(f"DROP INDEX IF EXISTS {self.name}")

    def describe(self):
        return f"Create the {self.name} HNSW index over chunk embeddings"

    @property
    def migration_name_fragment(self):
        return self.name.lower()


class EnableRowLevelSecurity(PostgresOnlyOperation):
    """Enable RLS on tables, without adding any policies.

    This is the whole protection, and the reasoning is worth stating plainly.
    Supabase grants `anon` and `authenticated` full access to every table in the
    public schema, and PostgREST will serve any of them to a request carrying
    the anon key — which ships in the frontend bundle. A table with RLS enabled
    and no policies denies those roles, so they cannot read or write rows
    through PostgREST.

    The Django service is unaffected: it connects as the database owner, and
    the owner bypasses RLS by design. That bypass is also why RLS cannot be the
    *only* thing enforcing ownership inside the app, which is what `access.py`
    and `library_service.py` are for. Together: RLS keeps everyone else out of
    Postgres entirely, and those modules keep one account out of another's rows
    within this service.
    """

    def __init__(self, tables: list[str]):
        self.tables = tables
        super().__init__()

    def _statements(self, verb: str) -> list[str]:
        return [f"ALTER TABLE {table} {verb} ROW LEVEL SECURITY" for table in self.tables]

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if self.is_postgres(schema_editor):
            for statement in self._statements("ENABLE"):
                schema_editor.execute(statement)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if self.is_postgres(schema_editor):
            for statement in self._statements("DISABLE"):
                schema_editor.execute(statement)

    def describe(self):
        return f"Enable row level security on {', '.join(self.tables)}"

    @property
    def migration_name_fragment(self):
        return "enable_row_level_security_on_" + "_and_".join(self.tables)
