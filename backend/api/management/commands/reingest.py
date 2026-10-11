from __future__ import annotations

import uuid

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from api.models import Document, DocumentStage


class Command(BaseCommand):
    help = "Re-enqueue ready documents so the worker rebuilds their chunks."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--document",
            type=uuid.UUID,
            action="append",
            help="Only re-enqueue this document id. Repeatable. Includes failed documents.",
        )
        parser.add_argument(
            "--library",
            type=uuid.UUID,
            help="Only re-enqueue documents in this library.",
        )

    def handle(self, *args, **options) -> None:
        if options["document"]:
            documents = Document.objects.filter(
                id__in=options["document"],
                stage__in=(DocumentStage.READY, DocumentStage.FAILED),
            )
        else:
            documents = Document.objects.filter(stage=DocumentStage.READY)

        if options["library"]:
            documents = documents.filter(library_id=options["library"])

        count = documents.update(
            stage=DocumentStage.QUEUED,
            error_message="",
            updated_at=timezone.now(),
        )

        if not count:
            raise CommandError("No ready documents matched, so nothing was queued.")

        self.stdout.write(
            self.style.SUCCESS(
                f"Queued {count} document(s). Run the worker to rebuild them: "
                "python manage.py run_pipeline"
            )
        )
