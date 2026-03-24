# ==========================================================
# File: review_repository.py
# Purpose: Database repository for storing and retrieving
#          AI code review reports
# ==========================================================

import json
from typing import List, Dict, Optional

from database.connection import get_connection


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