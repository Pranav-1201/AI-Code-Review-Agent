# ==========================================================
# File: celery_app.py
# Purpose: Celery application for out-of-process scan dispatch
#          (Phase 6 / Chunk 5 — real job queue).
# ==========================================================
#
# Scan work used to run in-process via FastAPI BackgroundTasks: a scan died
# with the web process and could not scale past one box. This moves dispatch
# onto a real broker so a separate worker container runs scans.
#
# Broker / backend are ENV-DRIVEN:
#   CELERY_BROKER_URL      e.g. redis://redis:6379/0   (docker-compose)
#   CELERY_RESULT_BACKEND  e.g. redis://redis:6379/1   (optional)
#
# When CELERY_BROKER_URL is UNSET (the test suite, CI, a bare local run) the
# app falls back to EAGER mode: .delay() runs the task synchronously in-process,
# so every existing route/test keeps working with no broker present. Real async
# dispatch happens only when a broker URL is configured. Native-Windows-without-
# Docker is deliberately not a supported *async* path — see DEPLOYMENT.md.
#
# Scan STATE (progress + final result) is not carried over Celery's result
# backend; it is persisted to the SQLite scan store (scan_manager, SCAN_DB_PATH)
# which the API reads back via GET /scan/{id}. In docker-compose that DB lives
# on a volume shared by the api and worker containers. Celery only carries the
# dispatch, so the result backend is optional.

import os

from celery import Celery
from celery.signals import worker_ready

_BROKER_URL = os.getenv("CELERY_BROKER_URL", "").strip()
_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "").strip()

# No broker configured -> run tasks eagerly and synchronously in-process.
_EAGER = not bool(_BROKER_URL)

celery_app = Celery(
    "etproject",
    broker=_BROKER_URL or "memory://",
    backend=_RESULT_BACKEND or "cache+memory://",
    # The worker discovers the scan task by importing this module.
    include=["backend.app.services.tasks"],
)

celery_app.conf.update(
    task_always_eager=_EAGER,
    # In eager mode surface task exceptions to the caller (tests rely on this);
    # the real run_scan_pipeline catches its own errors, so this is a no-op there.
    task_eager_propagates=True,
    # A scan is long-running: don't let one worker prefetch a backlog it can't
    # start, and track the 'started' state for observability.
    worker_prefetch_multiplier=1,
    task_track_started=True,
    # Keep broker startup resilient if the worker races Redis coming up.
    broker_connection_retry_on_startup=True,
    result_expires=3600,
)


@worker_ready.connect
def _recover_on_worker_ready(**_kwargs):
    """Reconcile zombie scans when a *real* worker boots (broker mode).

    Item 3 (zombie recovery) ran this in the API's startup lifespan, which was
    correct when the API and the scan runner were the same process. Now that the
    worker is a separate container, the WORKER is the process whose death orphans
    an in-flight scan — so recovery belongs at worker startup. (In eager mode
    there is no separate worker and the API lifespan still does it; see main.py.)

    Assumes a single worker service, as docker-compose ships. Multiple concurrent
    workers would need heartbeat-scoped recovery instead of reconcile-all — see
    DEPLOYMENT.md.
    """
    # Imported lazily so importing this module never drags in the scan store.
    from backend.app.services.scan_manager import recover_interrupted_scans

    try:
        recovered = recover_interrupted_scans()
        if recovered:
            print(f"[worker] recovered {recovered} interrupted scan(s) from a previous run")
    except Exception as e:  # never block the worker from coming up
        print(f"[worker] scan recovery skipped: {e!r}")
