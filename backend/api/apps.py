from __future__ import annotations

import logging
import sys

from django.apps import AppConfig
from django.core.checks import Error, Warning, register

logger = logging.getLogger(__name__)

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


#: Commands that never serve requests, so they must not start a worker. A
#: worker during `migrate` would try to ingest before the tables exist; during
#: `run_pipeline` it would simply compete with the command the operator asked
#: for. `runserver` and the WSGI/ASGI entry points are the ones that serve.
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
        """Start the ingestion worker, when this process should have one.

        An upload only creates a queued row, so without a worker documents never
        leave "queued" and chat answers decline for want of context. Running the
        worker here means it starts with the server, which is the only way it
        reliably gets started at all.
        """
        from django.conf import settings

        if settings.TESTING:
            # The suite drives ingestion directly and asserts on exact counts; a
            # background thread would race it and make results depend on timing.
            return

        if not settings.RUN_PIPELINE_IN_PROCESS:
            # Running `manage.py run_pipeline` as its own process instead. The
            # advisory lock means the two arrangements can coexist safely.
            return

        if not _is_serving():
            return

        # The autoreloader runs this method in a supervising process that then
        # forks the real one. Starting a worker in the supervisor means two
        # threads, and the child's database connections are not the supervisor's,
        # so the lock is not enough to make that harmless.
        if _is_autoreload_supervisor():
            return

        from api import pipeline_worker

        pipeline_worker.start()


def _is_serving() -> bool:
    """True when this process is running a server rather than a management command.

    Checked against argv rather than a settings flag because there is no honest
    way to tell from configuration alone: `migrate` and `runserver` use the same
    settings module.
    """
    argv = sys.argv

    # `uvicorn api:app`, `gunicorn config.wsgi`, `hypercorn ...` put the server
    # name first with no subcommand.
    if argv and argv[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1] in {
        "gunicorn",
        "uvicorn",
        "daphne",
        "hypercorn",
    }:
        return True

    return any(command in _SERVING_COMMANDS for command in argv[1:])


def _is_autoreload_supervisor() -> bool:
    """True in the process that supervises `runserver --reload`.

    The supervisor has `RUN_MAIN` unset; the worker process it forks has
    `RUN_MAIN=true`. Only the latter serves requests.
    """
    import os

    return "runserver" in sys.argv and os.environ.get("RUN_MAIN") != "true"
