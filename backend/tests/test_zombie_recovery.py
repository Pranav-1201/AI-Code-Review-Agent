"""
Zombie-scan recovery guards (Phase 6 / Chunk 5).

Scan work runs in-process, so a scan left mid-flight by a killed process
can never resume — without reconciliation its row stays 'analyzing' forever
and the frontend polls a dead scan until its client deadline. These tests
pin: (1) recovery marks in-flight scans terminal as status='error', (2) it
never touches already-terminal scans and is idempotent, (3) complete_scan
now distinguishes an errored result from success, and (4) the app actually
runs recovery on startup (lifespan wiring — the part a unit test on the
function alone would miss).
"""

import os
import tempfile

import backend.app.services.scan_manager as sm


def _fresh_db(monkeypatch):
    """Point scan_manager at an isolated temp DB (mirrors phase0_1 _item5)."""
    db_path = os.path.join(tempfile.mkdtemp(), "scan_states.db")
    monkeypatch.setattr(sm, "_DB_PATH", db_path)
    monkeypatch.setattr(sm, "_conn", None)
    return db_path


def test_recover_marks_inflight_as_error(monkeypatch):
    _fresh_db(monkeypatch)

    scan_id = sm.create_scan("https://example.com/repo.git")
    sm.update_scan(scan_id, "analyzing", 42, stage="analysis",
                   stage_detail="halfway", total_files=7)

    recovered = sm.recover_interrupted_scans()
    assert recovered == 1

    got = sm.get_scan(scan_id)
    assert got["status"] == "error", got
    assert got["stage"] == "interrupted", got
    assert "restart" in got["result"]["error"].lower()
    # Top-level error surfaced for the frontend poller (status.error).
    assert got["error"] == got["result"]["error"]


def test_recover_leaves_terminal_scans_untouched(monkeypatch):
    _fresh_db(monkeypatch)

    done = sm.create_scan("repo-done")
    sm.complete_scan(done, {"health_score": 88})

    failed = sm.create_scan("repo-failed")
    sm.complete_scan(failed, {"error": "boom"})

    # Nothing in-flight -> nothing to reconcile.
    assert sm.recover_interrupted_scans() == 0

    assert sm.get_scan(done)["status"] == "complete"
    assert sm.get_scan(done)["result"]["health_score"] == 88
    assert sm.get_scan(failed)["status"] == "error"


def test_recover_is_idempotent(monkeypatch):
    _fresh_db(monkeypatch)

    sid = sm.create_scan("repo")
    sm.update_scan(sid, "cloning", 5)

    assert sm.recover_interrupted_scans() == 1
    # Second pass: the row is now terminal, so nothing is reconciled.
    assert sm.recover_interrupted_scans() == 0
    assert sm.get_scan(sid)["status"] == "error"


def test_complete_scan_distinguishes_error_from_success(monkeypatch):
    _fresh_db(monkeypatch)

    ok = sm.create_scan("ok")
    sm.complete_scan(ok, {"repository_summary": {"files_analyzed": 3}})
    ok_row = sm.get_scan(ok)
    assert ok_row["status"] == "complete"
    assert "error" not in ok_row  # additive key absent on success

    bad = sm.create_scan("bad")
    sm.complete_scan(bad, {"error": "clone failed"})
    bad_row = sm.get_scan(bad)
    assert bad_row["status"] == "error"
    assert bad_row["error"] == "clone failed"


def test_lifespan_runs_recovery_on_startup(monkeypatch):
    """The real product path: booting the app reconciles a leftover scan."""
    from fastapi.testclient import TestClient
    import main

    _fresh_db(monkeypatch)

    # Seed a scan stuck mid-flight, as if a previous process died.
    stuck = sm.create_scan("https://example.com/stuck.git")
    sm.update_scan(stuck, "analyzing", 40)
    assert sm.get_scan(stuck)["status"] == "analyzing"

    # Booting the app (entering the TestClient context) runs the lifespan
    # startup hook, which must reconcile the stuck scan.
    with TestClient(main.app):
        pass

    assert sm.get_scan(stuck)["status"] == "error"


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
