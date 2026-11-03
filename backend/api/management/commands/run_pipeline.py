from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from api.ingestion import ingest_pending, worker_lock


class Command(BaseCommand):
    help = "Process queued documents through parsing, chunking and embedding."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Keep polling for new documents instead of making one pass.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Documents to process per pass. Default 10.",
        )
        parser.add_argument(
            "--interval",
            type=float,
            default=5.0,
            help="Seconds to wait between passes with --loop. Default 5.",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Stop even if documents are still queued. The default for one pass.",
        )

    def handle(self, *args, **options) -> None:
        looping = options["loop"] and not options["once"]
        limit = options["limit"]
        interval = options["interval"]

        self.stdout.write(
            f"Pipeline worker started ({'looping' if looping else 'single pass'}, "
            f"limit {limit} per pass)."
        )

        try:
            while True:
                # Same lock as the in-process worker; else both run one document.
                with worker_lock() as acquired:
                    if not acquired:
                        # Not an error: the web process's worker already owns it.
                        self.stdout.write(
                            "Another ingestion worker is running; standing down. "
                            "Set REVIA_RUN_PIPELINE_IN_PROCESS=off to stop the "
                            "in-process worker if you meant to run this instead."
                        )
                        return

                    summary = ingest_pending(limit=limit)

                self.stdout.write(
                    "attempted {attempted}  ready {ready}  failed {failed}  "
                    "requeued {retried}  reaped {reaped}".format(**summary)
                )

                if not looping or summary["attempted"] < limit:
                    if not looping:
                        break
                    time.sleep(interval)
                    continue

                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write("Stopping. Any document mid-pipeline stays where it is.")
