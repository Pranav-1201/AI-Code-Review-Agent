# ==========================================================
# File: connection.py
# Purpose: SQLite database connection and initialization
# ==========================================================

import sqlite3
from pathlib import Path

# ----------------------------------------------------------
# Database Path
# ----------------------------------------------------------

DB_PATH = Path("backend/database/reviews.db")


# ----------------------------------------------------------
# Get Database Connection
# ----------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    """
    Create a SQLite database connection.
    """

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    return conn


# ----------------------------------------------------------
# Initialize Database
# ----------------------------------------------------------

def init_db():
    """
    Create required database tables if they do not exist.
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repo_name TEXT,
        commit_id TEXT,
        score REAL,
        summary TEXT,
        report_json TEXT
    )
    """)

    # Optional index for faster queries
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_repo_commit
    ON reviews (repo_name, commit_id)
    """)

    conn.commit()
    conn.close()