from __future__ import annotations

from django.apps import AppConfig
from django.core.checks import Error, Warning, register

#: The dimension baked into migration 0002 when the chunks table was created.
#: pgvector's column type and the HNSW index are both built for this width, so
#: changing the configured dimension without a migration leaves a column that
#: silently rejects the new vectors at insert time — or worse, accepts them and
#: makes similarity search meaningless.
MIGRATED_EMBEDDING_DIM = 384


@register()
def check_embedding_dimension(app_configs, **kwargs):
    """Warn when the configured embedding width no longer matches the database.

    The model field reads `settings.EMBEDDING_DIM`, so the model and the setting
    can never disagree. What can drift is the *migration*, which froze the width
    when the column was created. Comparing against that is the only way to catch
    someone raising the setting expecting new embeddings to just work.
    """
    from django.conf import settings

    configured = settings.EMBEDDING_DIM
    if configured == MIGRATED_EMBEDDING_DIM:
        return []

    return [
        Error(
            f"EMBEDDING_DIM is {configured} but the chunks.embedding column was "
            f"created with {MIGRATED_EMBEDDING_DIM} dimensions.",
            hint=(
                "The vector column and its HNSW index are fixed at "
                f"{MIGRATED_EMBEDDING_DIM}. Either set EMBEDDING_DIM back, or "
                "write a migration to resize the column and re-embed every stored "
                "chunk — vectors from a different model are not comparable even at "
                "the same width."
            ),
            id="api.E001",
        )
    ]


@register()
def check_allowed_upload_extensions(app_configs, **kwargs):
    """The extension allowlist has to be non-empty and lower-case.

    Extension checks compare against a lower-cased filename, so an upper-case
    entry silently matches nothing. A typo there would reject every upload while
    looking correct in the config.
    """
    from django.conf import settings

    allowed = settings.ALLOWED_UPLOAD_EXTENSIONS
    if not allowed:
        return [
            Error(
                "ALLOWED_UPLOAD_EXTENSIONS is empty, so no upload can ever be accepted.",
                id="api.E002",
            )
        ]

    bad = [item for item in allowed if item != item.lower() or not item.startswith(".")]
    if bad:
        return [
            Warning(
                f"ALLOWED_UPLOAD_EXTENSIONS contains entries that will never match: {bad}.",
                hint="Use lower-case extensions including the leading dot, e.g. '.pdf'.",
                id="api.W001",
            )
        ]

    return []


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
    label = "api"
    verbose_name = "EndNote API"
