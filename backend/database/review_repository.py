import json
from database.connection import get_connection


def save_review(repo_name, commit_id, score, summary, report):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO reviews (repo_name, commit_id, score, summary, report_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (repo_name, commit_id, score, summary, json.dumps(report))
    )

    conn.commit()

    # Get the inserted review ID
    review_id = cursor.lastrowid

    conn.close()

    return review_id


def get_reviews_by_repo(repo_name):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, report_json FROM reviews WHERE repo_name=?",
        (repo_name,)
    )

    rows = cursor.fetchall()
    conn.close()

    return rows


def get_review_by_id(review_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT report_json FROM reviews WHERE id=?",
        (review_id,)
    )

    row = cursor.fetchone()
    conn.close()

    return row