"""
Live-surface tests for the FastAPI app (Phase 5 follow-up).

Unlike test_explanation.py / test_feedback.py (which call engine functions
directly), these drive the REAL routes through Starlette's TestClient, so they
cover routing, the Pydantic request models, and the background-task wiring —
the parts that "AST-parses clean" cannot prove. The Anthropic layer stays gated
OFF, so nothing here touches the network.

Regression guard (test_repo_file_report_carries_explanation_source): the
`explanation_source` label is computed in analyze_code but was dropped before
the repository-scan file report, so a real scan silently lost the
llm|deterministic provenance. That gap was invisible to tests that only called
analyze_code in isolation.
"""

import os

import pytest

# The app imports fastapi; the TestClient needs httpx. Skip cleanly if either
# is missing (e.g. a bare interpreter without the API extras installed).
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

os.environ.pop("ENABLE_ANTHROPIC", None)
os.environ.pop("ANTHROPIC_API_KEY", None)


@pytest.fixture()
def client(tmp_path):
    """TestClient bound to an isolated temp DB so the precision math is clean.

    record_feedback/get_precision_estimate call connection.get_connection(),
    which reads connection.DB_PATH at call time, so pointing the global at a
    temp file (and re-running init_db) is enough — no module reloads needed.
    """
    from fastapi.testclient import TestClient
    import backend.database.connection as connection
    import main

    original = connection.DB_PATH
    connection.DB_PATH = tmp_path / "reviews.db"
    connection.init_db()
    try:
        with TestClient(main.app) as c:
            yield c, main
    finally:
        connection.DB_PATH = original


def test_feedback_roundtrip_and_precision(client):
    c, _ = client

    # Fresh DB: no votes yet -> precision is None, not a fake 0.0/1.0.
    assert c.get("/feedback/precision").json()["precision"] is None

    for _ in range(3):
        r = c.post("/feedback",
                   json={"review_id": 1, "finding_key": "a.py:1:eval", "vote": "up"})
        assert r.status_code == 200
        assert r.json()["status"] == "recorded"

    r = c.post("/feedback",
               json={"review_id": 1, "finding_key": "a.py:2:pickle", "vote": "down"})
    assert r.json()["precision"] == {"up": 3, "down": 1, "total": 4, "precision": 0.75}

    # Invalid vote must return an error object, never a 500.
    r = c.post("/feedback",
               json={"review_id": 1, "finding_key": "x", "vote": "meh"})
    assert r.status_code == 200
    assert r.json()["status"] == "error"

    # Persisted and read back.
    assert c.get("/feedback/precision").json() == {
        "up": 3, "down": 1, "total": 4, "precision": 0.75}


def test_scan_threads_explanation_depth(client):
    """POST /scan with explanation_depth must reach the background pipeline.

    We stub run_scan_pipeline to capture what the route actually passes it, so
    this proves the RepoRequest field survives the request -> background-task
    hop (the depth default would silently mask a dropped value otherwise).
    """
    c, main = client

    captured = {}

    def fake_pipeline(scan_id, repo_url, explanation_depth="senior"):
        captured["scan_id"] = scan_id
        captured["repo_url"] = repo_url
        captured["depth"] = explanation_depth

    original = main.run_scan_pipeline
    main.run_scan_pipeline = fake_pipeline
    try:
        r = c.post("/scan",
                   json={"repo_path": "some/repo", "explanation_depth": "junior"})
        assert r.status_code == 200
        assert "scan_id" in r.json()
    finally:
        main.run_scan_pipeline = original

    assert captured.get("depth") == "junior", captured
    assert captured.get("repo_url") == "some/repo"


def test_scan_explanation_depth_defaults_to_senior(client):
    c, main = client
    captured = {}

    def fake_pipeline(scan_id, repo_url, explanation_depth="senior"):
        captured["depth"] = explanation_depth

    original = main.run_scan_pipeline
    main.run_scan_pipeline = fake_pipeline
    try:
        r = c.post("/scan", json={"repo_path": "some/repo"})  # omit depth
        assert r.status_code == 200
    finally:
        main.run_scan_pipeline = original

    assert captured.get("depth") == "senior", captured


def test_repo_file_report_carries_explanation_source():
    """The repository-scan file report must carry the explanation_source label.

    This is the durable guard for the dropped-label regression the live server
    check surfaced: analyze_code returns explanation_source under result
    ["analysis"], but analyze_single_file did not copy it onto the file report,
    so a real scan produced zero explanation_source labels.
    """
    from backend.app.services.repository_review_engine import analyze_single_file
    from backend.app.analysis.heuristic_refactor_engine import HeuristicRefactorEngine

    file_data = {
        "content": "def f(x):\n    return x + 1\n",
        "file_name": "sample.py",
        "file_path": "sample.py",
        "language": "python",
    }
    report = analyze_single_file(file_data, HeuristicRefactorEngine(),
                                 explanation_depth="senior")

    assert "explanation_source" in report, "file report dropped explanation_source"
    assert report["explanation_source"] in ("llm", "deterministic")
    # LLM gated off -> the label must read deterministic.
    assert report["explanation_source"] == "deterministic"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
