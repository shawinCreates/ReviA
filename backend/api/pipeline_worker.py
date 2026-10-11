from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.db import connections

from api import ingestion

logger = logging.getLogger(__name__)

#: Guards `start`. Two callers racing to start the worker would otherwise spawn
#: two threads in one process, both polling, which the advisory lock would
#: tolerate but which doubles the idle database traffic for no benefit.
_start_lock = threading.Lock()

_thread: threading.Thread | None = None
#: Set so a test or a management command can ask whether the worker is running
#: without reaching into the module's internals.
_started = threading.Event()


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


def start() -> bool:
    global _thread

    with _start_lock:
        if is_running():
            return False

        thread = threading.Thread(
            target=_run,
            name="revia-pipeline",
            # Daemon so a normal interpreter shutdown is not held up waiting for
            # a pass that is sleeping between polls.
            daemon=True,
        )
        thread.start()
        _thread = thread
        _started.set()
        logger.info("Ingestion worker started in-process")
        return True


def stop(timeout: float = 5.0) -> None:
    global _thread

    with _start_lock:
        thread = _thread
        _thread = None
        _started.clear()

    if thread is not None and thread.is_alive():
        # The loop checks this between passes, so a pass already under way runs
        # to completion rather than being interrupted mid-transaction.
        stop_requested.set()
        thread.join(timeout=timeout)

#: Read by `_run` between passes. Separate from `_thread` because a thread that
#: is mid-pass must finish that pass before noticing a stop request.
stop_requested = threading.Event()


def _run() -> None:
    while not stop_requested.is_set():
        try:
            worked = _pass()
        except Exception:
            # Nothing above this catches anything. Without this the thread dies,
            # uploads stop progressing, and the symptom reads as "ingestion is
            # broken" rather than "a background thread exited".
            logger.exception("Ingestion worker pass failed; continuing")
            worked = False

        # Between passes, not only when idle: a connection left open by a failed
        # pass would otherwise stay checked out for the life of the thread.
        connections.close_all()

        if stop_requested.wait(_interval(worked)):
            return


def _pass() -> bool:
    with ingestion.worker_lock() as acquired:
        if not acquired:
            # Another worker has it. It is doing this work; standing by is the
            # correct behaviour, not a failure.
            logger.debug("Ingestion worker stood down: another worker holds the lock")
            return False

        summary = ingestion.ingest_pending(limit=_batch_size())

    if summary["attempted"] or summary["reaped"]:
        logger.info(
            "Ingestion pass: attempted {attempted} ready {ready} failed {failed} "
            "requeued {retried} reaped {reaped}".format(**summary)
        )
    return bool(summary["attempted"] or summary["reaped"])


def _interval(worked: bool) -> float:
    if worked:
        return settings.PIPELINE_BUSY_SECONDS
    return settings.PIPELINE_IDLE_SECONDS


def _batch_size() -> int:
    return settings.PIPELINE_BATCH_SIZE
