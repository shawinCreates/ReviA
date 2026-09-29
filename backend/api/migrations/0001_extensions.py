"""
Extensions.

Runs before the schema because `chunk.embedding` is declared vector(1024) and
its HNSW index requires the `vector_cosine_ops` operator class. Creating the
tables first would fail with "operator class does not exist".

`vector` is created here rather than assumed. Supabase does not enable it on a
new project by default, and the failure mode if it is missing is a migration
error rather than a clear message, so this states the requirement explicitly.

`pgcrypto` supplies gen_random_uuid(), which the model layer relies on for
id defaults. It is already present on Supabase, so this is defensive and
idempotent rather than load-bearing.
"""

from django.db import migrations


class Migration(migrations.Migration):
    initial = True

    dependencies: list = []

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS vector;",
            reverse_sql="DROP EXTENSION IF EXISTS vector;",
        ),
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS pgcrypto;",
            reverse_sql="DROP EXTENSION IF EXISTS pgcrypto;",
        ),
    ]
