from __future__ import annotations

import logging
import sys

from django.apps import AppConfig
from django.core.checks import Error, Warning, register

logger = logging.getLogger(__name__)

#: The dimension migration 0002 baked into chunks.embedding and its HNSW index.
MIGRATED_EMBEDDING_DIM = 384


@register()
def check_embedding_dimension(app_configs, **kwargs):
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

#: Commands that serve requests; only these may start the worker.
_SERVING_COMMANDS = frozenset({"runserver", "gunicorn", "uvicorn", "daphne", "hypercorn"})


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
    label = "api"
    verbose_name = "ReviA API"

    def ready(self) -> None:
        super().ready()
        self._maybe_start_pipeline_worker()

    def _maybe_start_pipeline_worker(self) -> None:
        from django.conf import settings

        if settings.TESTING:
            # The suite drives ingestion directly; a thread would race it.
            return

        if not settings.RUN_PIPELINE_IN_PROCESS:
            # The advisory lock makes manage.py run_pipeline safe alongside.
            return

        if not _is_serving():
            return

        # The autoreloader's supervisor would double threads and split connections.
        if _is_autoreload_supervisor():
            return

        from api import pipeline_worker

        pipeline_worker.start()


def _is_serving() -> bool:
    argv = sys.argv

    if argv and argv[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1] in {
        "gunicorn",
        "uvicorn",
        "daphne",
        "hypercorn",
    }:
        return True

    return any(command in _SERVING_COMMANDS for command in argv[1:])


def _is_autoreload_supervisor() -> bool:
    import os

    return "runserver" in sys.argv and os.environ.get("RUN_MAIN") != "true"
