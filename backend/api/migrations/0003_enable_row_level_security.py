from django.db import migrations

from api.migration_ops import EnableRowLevelSecurity


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0002_library_document_chunk_and_more"),
    ]

    operations = [
        EnableRowLevelSecurity(["profiles", "libraries", "documents", "chunks"]),
    ]
