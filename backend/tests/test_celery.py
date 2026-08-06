"""
Celery job-queue wiring (Phase 6 / Chunk 5).

Offline + deterministic: no broker, no Redis, no worker subprocess. These pin the
in-process (eager) contract the whole suite/CI depends on, plus the worker-vs-API
split of zombie recovery that decoupling the worker introduced:

  1. With no CELERY_BROKER_URL, dispatch is eager (in-process) — no broker needed.
  2. run_scan_task defers to main.run_scan_pipeline resolved at call time, so the
     live-API monkeypatch keeps working and the heavy logic stays out of the task.
  3. In BROKER mode the worker owns zombie recovery (worker_ready signal), and the
     API lifespan must NOT run recovery — otherwise an API restart would wrongly
     mark a scan a live worker is still processing as 'error'.

The real out-of-process round-trip over a broker is exercised separately by
backend/scripts/queue_roundtrip.py (run for release evidence, kept out of the
default suite like the benchmark real-repo half).
"""

import os
import tempfile

import pytest

pytest.importorskip("celery")

import backend.app.services.scan_manager as sm
from backend.app.services import tasks
from backend.app.services.celery_app import celery_app, _recover_on_worker_ready


def _fresh_db(monkeypatch):
    """Point scan_manager at an isolated temp DB (mirrors test_zombie_recovery)."""
    db_path = os.path.join(tempfile.mkdtemp(), "scan_states.db")
    monkeypatch.setattr(sm, "_DB_PATH", db_path)
    monkeypatch.setattr(sm, "_conn", None)
    return db_path


def test_eager_by_default_without_broker():
    # This test env sets no CELERY_BROKER_URL, so dispatch must be synchronous
    # in-process — the suite and CI never stand up a broker.
    assert celery_app.conf.task_always_eager is True


def test_scan_task_defers_to_run_scan_pipeline(monkeypatch):
    """The task must call main.run_scan_pipeline by attribute at call time."""
    import main

    captured = {}

    def fake_pipeline(scan_id, repo_url, explanation_depth="senior"):
        captured.update(scan_id=scan_id, repo_url=repo_url, depth=explanation_depth)
        return {"ok": True}

    monkeypatch.setattr(main, "run_scan_pipeline", fake_pipeline)

    # .apply() runs the task locally and binds `self`, without needing a broker.
    result = tasks.run_scan_task.apply(args=["sid-1", "some/repo", "junior"]).get()

    assert captured == {"scan_id": "sid-1", "repo_url": "some/repo", "depth": "junior"}
    assert result == {"ok": True}


def test_worker_ready_signal_recovers_zombie_scans(monkeypatch):
    """A booting worker reconciles scans orphaned by a previous worker."""
    _fresh_db(monkeypatch)

    stuck = sm.create_scan("https://example.com/stuck.git")
    sm.update_scan(stuck, "analyzing", 40)
    assert sm.get_scan(stuck)["status"] == "analyzing"

    _recover_on_worker_ready()  # the worker_ready handler

    assert sm.get_scan(stuck)["status"] == "error"


def test_api_lifespan_skips_recovery_in_broker_mode(monkeypatch):
    """In broker mode the API must NOT run recovery — the worker owns it.

    Otherwise restarting the API would clobber a scan a live worker is still
    running. Pins the fix for the regression decoupling the worker introduced.
    """
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    import main

    _fresh_db(monkeypatch)

    # Simulate a real broker being configured: the app is not eager.
    monkeypatch.setattr(celery_app.conf, "task_always_eager", False)

    stuck = sm.create_scan("https://example.com/live.git")
    sm.update_scan(stuck, "analyzing", 40)

    with TestClient(main.app):  # runs the startup lifespan
        pass

    # The API left the in-flight scan alone — recovery is the worker's job now.
    assert sm.get_scan(stuck)["status"] == "analyzing"


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
