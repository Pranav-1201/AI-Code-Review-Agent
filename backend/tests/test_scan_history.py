"""
Scan-history list (Fix K).

The frontend Scan History page must survive a page reload, so history is read
from the persisted scan store instead of browser memory. These tests pin:
(1) list_scans extracts health/files/issues from the stored result payload,
(2) it returns only COMPLETED scans, newest-first, (3) it honours the limit,
and (4) the GET /scans endpoint exposes it.
"""

import os
import time
import tempfile

import backend.app.services.scan_manager as sm


def _fresh_db(monkeypatch):
    """Point scan_manager at an isolated temp DB (mirrors test_zombie_recovery)."""
    db_path = os.path.join(tempfile.mkdtemp(), "scan_states.db")
    monkeypatch.setattr(sm, "_DB_PATH", db_path)
    monkeypatch.setattr(sm, "_conn", None)
    return db_path


def _complete(repo, health, files, issues_per_file):
    """Create + complete a scan whose result mirrors run_pipeline's shape."""
    sid = sm.create_scan(repo)
    result = {
        "repository_summary": {"health_score": health, "files_analyzed": files},
        "file_reports": [{"issues": [{}] * n} for n in issues_per_file],
    }
    sm.complete_scan(sid, result)
    return sid


def test_list_scans_extracts_summary_fields(monkeypatch):
    _fresh_db(monkeypatch)

    sid = _complete("https://github.com/acme/webapp", health=73, files=12,
                    issues_per_file=[3, 4, 0])  # 7 issues across files

    rows = sm.list_scans()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == sid
    assert row["repo"] == "https://github.com/acme/webapp"
    assert row["health_score"] == 73
    assert row["files_analyzed"] == 12
    assert row["issues_found"] == 7
    assert row["timestamp"]  # created_at populated


def test_list_scans_newest_first(monkeypatch):
    _fresh_db(monkeypatch)

    first = _complete("repo-old", 50, 1, [1])
    time.sleep(0.01)  # guarantee a distinct created_at even on a coarse clock
    second = _complete("repo-new", 90, 2, [0, 0])

    ids = [r["id"] for r in sm.list_scans()]
    assert ids == [second, first]  # created_at DESC


def test_list_scans_omits_non_complete(monkeypatch):
    _fresh_db(monkeypatch)

    done = _complete("done", 80, 3, [1])

    inflight = sm.create_scan("inflight")
    sm.update_scan(inflight, "analyzing", 40)

    failed = sm.create_scan("failed")
    sm.complete_scan(failed, {"error": "clone failed"})

    ids = [r["id"] for r in sm.list_scans()]
    assert ids == [done]


def test_list_scans_honours_limit(monkeypatch):
    _fresh_db(monkeypatch)

    for i in range(5):
        _complete(f"repo-{i}", 70, 1, [1])
        time.sleep(0.005)

    assert len(sm.list_scans(limit=3)) == 3


def test_list_scans_legacy_row_degrades_to_zeros(monkeypatch):
    _fresh_db(monkeypatch)

    # A completed scan whose result lacks a summary (older/partial payload).
    sid = sm.create_scan("legacy")
    sm.complete_scan(sid, {"note": "no summary here"})

    rows = sm.list_scans()
    assert len(rows) == 1
    assert rows[0]["health_score"] == 0
    assert rows[0]["files_analyzed"] == 0
    assert rows[0]["issues_found"] == 0


def test_scans_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    import main

    _fresh_db(monkeypatch)
    _complete("https://github.com/acme/api", 88, 5, [2, 1])

    with TestClient(main.app) as client:
        resp = client.get("/scans")

    assert resp.status_code == 200
    body = resp.json()
    assert "scans" in body
    assert len(body["scans"]) == 1
    assert body["scans"][0]["health_score"] == 88
    assert body["scans"][0]["issues_found"] == 3


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
