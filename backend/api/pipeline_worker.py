from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.db import connections

from api import ingestion

logger = logging.getLogger(__name__)

#: Guards start(); racers would spawn two polling threads.
_start_lock = threading.Lock()

_thread: threading.Thread | None = None
#: Lets a test or command ask whether the worker runs, without internals.
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
        # Checked between passes; a pass under way runs to completion.
        stop_requested.set()
        thread.join(timeout=timeout)

#: Read between passes; a mid-pass thread finishes before noticing a stop.
stop_requested = threading.Event()


def _run() -> None:
    while not stop_requested.is_set():
        try:
            worked = _pass()
        except Exception:
            logger.exception("Ingestion worker pass failed; continuing")
            worked = False

        # Also after failed passes; else a connection lingers for the thread's life.
        connections.close_all()

        if stop_requested.wait(_interval(worked)):
            return


def _pass() -> bool:
    with ingestion.worker_lock() as acquired:
        if not acquired:
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
