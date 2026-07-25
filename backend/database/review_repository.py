# ==========================================================
# File: review_repository.py
# Purpose: Database repository for storing and retrieving
#          AI code review reports
# ==========================================================

import json
from typing import List, Dict, Optional

from backend.database.connection import get_connection


# ----------------------------------------------------------
# Save Review
# ----------------------------------------------------------

def save_review(
    repo_name: str,
    commit_id: str,
    score: float,
    summary: str,
    report: Dict
) -> int:
    """
    Save a review report in the database.
    """

    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO reviews (repo_name, commit_id, score, summary, report_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (repo_name, commit_id, score, summary, json.dumps(report))
        )

        review_id = cursor.lastrowid

        conn.commit()

    return review_id


# ----------------------------------------------------------
# Get Reviews by Repository
# ----------------------------------------------------------

def get_reviews_by_repo(repo_name: str) -> List[Dict]:
    """
    Retrieve all reviews for a repository.
    """

    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, report_json
            FROM reviews
            WHERE repo_name = ?
            """,
            (repo_name,)
        )

        rows = cursor.fetchall()

    results = []

    for row in rows:
        results.append({
            "id": row["id"],
            "report": json.loads(row["report_json"])
        })

    return results


# ----------------------------------------------------------
# Get Review by ID
# ----------------------------------------------------------

def get_review_by_id(review_id: int) -> Optional[Dict]:
    """
    Retrieve a specific review by ID.
    """

    with get_connection() as conn:

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT report_json
            FROM reviews
            WHERE id = ?
            """,
            (review_id,)
        )

        row = cursor.fetchone()

    if row is None:
        return None

    return json.loads(row["report_json"])


# ----------------------------------------------------------
# Feedback loop (Phase 5)
# ----------------------------------------------------------

def record_feedback(review_id: int, finding_key: str, vote: str) -> int:
    """
    Persist a thumbs up/down on a specific finding.

    vote must be 'up' (true positive) or 'down' (false positive).
    Returns the new feedback row id. Raises ValueError on a bad vote.
    """
    if vote not in ("up", "down"):
        raise ValueError(f"vote must be 'up' or 'down', got {vote!r}")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO feedback (review_id, finding_key, vote)
            VALUES (?, ?, ?)
            """,
            (review_id, finding_key, vote),
        )
        feedback_id = cursor.lastrowid
        conn.commit()

    return feedback_id


def get_precision_estimate() -> Dict:
    """
    Running precision from all recorded feedback:
        precision = up_votes / (up_votes + down_votes)

    Returns {"up", "down", "total", "precision"}. precision is None until
    at least one vote exists, so a fresh install does not report a fake 0/1.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                SUM(CASE WHEN vote = 'up'   THEN 1 ELSE 0 END) AS up,
                SUM(CASE WHEN vote = 'down' THEN 1 ELSE 0 END) AS down
            FROM feedback
            """
        )
        row = cursor.fetchone()

    up = row["up"] or 0
    down = row["down"] or 0
    total = up + down
    precision = round(up / total, 4) if total > 0 else None

    return {"up": up, "down": down, "total": total, "precision": precision}