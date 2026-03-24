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

# Ensure database directory exists
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------
# Get Database Connection
# ----------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    """
    Create a SQLite database connection.

    This function also guarantees that the database
    schema has been initialized before use.
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

    This function is safe to call multiple times because
    it uses CREATE TABLE IF NOT EXISTS.
    """

    conn = get_connection()
    cursor = conn.cursor()

    # ------------------------------------------------------
    # Reviews Table
    # ------------------------------------------------------

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

    # ------------------------------------------------------
    # Index for faster queries
    # ------------------------------------------------------

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_repo_commit
    ON reviews (repo_name, commit_id)
    """)

    conn.commit()
    conn.close()


# ----------------------------------------------------------
# Automatic Database Initialization
# ----------------------------------------------------------

# Ensure database schema exists when module loads
init_db()