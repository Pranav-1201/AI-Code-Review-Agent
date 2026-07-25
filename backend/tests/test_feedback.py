"""
Phase 5 feedback-loop tests: thumbs up/down persistence and the running
precision estimate. Runs against an ISOLATED temp SQLite DB (DB_PATH is
monkeypatched) so it never touches the real reviews.db.
"""

import importlib

import pytest


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """review_repository wired to a fresh temp database."""
    from backend.database import connection
    monkeypatch.setattr(connection, "DB_PATH", tmp_path / "test.db")
    connection.init_db()
    review_repository = importlib.import_module("backend.database.review_repository")
    return review_repository


def test_precision_none_when_no_feedback(repo):
    est = repo.get_precision_estimate()
    assert est == {"up": 0, "down": 0, "total": 0, "precision": None}


def test_running_precision(repo):
    for _ in range(3):
        repo.record_feedback(1, "views.py:10:eval", "up")
    repo.record_feedback(1, "views.py:99:subprocess", "down")

    est = repo.get_precision_estimate()
    assert est["up"] == 3
    assert est["down"] == 1
    assert est["total"] == 4
    assert est["precision"] == 0.75


def test_invalid_vote_rejected(repo):
    with pytest.raises(ValueError):
        repo.record_feedback(1, "x", "maybe")


def test_record_returns_row_id(repo):
    fid = repo.record_feedback(7, "a.py:1:pickle", "up")
    assert isinstance(fid, int) and fid >= 1
