"""Run the ingestion pipeline over queued documents."""

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
                # The same lock the in-process worker takes. Without it this
                # command and that thread would each pick up the same queued
                # document and process it twice, because `advance_stage` writes
                # from a stale in-memory copy rather than a locked read.
                with worker_lock() as acquired:
                    if not acquired:
                        # Not an error: ingestion is already happening, which is
                        # the normal state when the web process has the worker
                        # in it. Standing down is what keeps it correct.
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

                # Nothing to do: sleep before asking again, rather than
                # hammering the database in a tight loop. In a single pass there
                # is nothing left to wait for.
                if not looping or summary["attempted"] < limit:
                    if not looping:
                        break
                    time.sleep(interval)
                    continue

                time.sleep(interval)
        except KeyboardInterrupt:
            # Expected: this command is meant to be stopped with Ctrl-C and run
            # again, and a document mid-pipeline is left in its current stage
            # for the next pass rather than being abandoned silently.
            self.stdout.write("Stopping. Any document mid-pipeline stays where it is.")
