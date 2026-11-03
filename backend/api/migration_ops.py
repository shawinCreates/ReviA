from __future__ import annotations

from django.db.migrations.operations.base import Operation


class PostgresOnlyOperation(Operation):
    def state_forwards(self, app_label, state):
        pass

    def is_postgres(self, schema_editor) -> bool:
        return schema_editor.connection.vendor == "postgresql"

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        raise NotImplementedError

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        raise NotImplementedError

    def allows_reference_model(self, operation, app_label, model_name):
        return False


class CreateVectorExtension(PostgresOnlyOperation):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if self.is_postgres(schema_editor):
            schema_editor.execute("CREATE EXTENSION IF NOT EXISTS vector")

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        # Left installed: dropping a shared extension breaks other dependents.
        return

    def describe(self):
        return "Create the pgvector extension if the backend is PostgreSQL"

    @property
    def migration_name_fragment(self):
        return "create_vector_extension"


class CreateHnswEmbeddingIndex(PostgresOnlyOperation):
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
