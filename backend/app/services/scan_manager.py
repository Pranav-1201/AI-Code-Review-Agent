# ==========================================================
# File: scan_manager.py
# Purpose: Track repository scan progress with stage details
# Persistence: SQLite (survives process restarts)
# ==========================================================

import os
import json
import sqlite3
import uuid
from typing import Dict, Optional


# ----------------------------------------------------------
# Database Configuration
# ----------------------------------------------------------
# DB path is configurable via SCAN_DB_PATH environment variable.
# Defaults to scan_states.db in the current working directory.
# Set SCAN_DB_PATH=/path/to/data/scan_states.db in production
# to store the file on a persistent volume.
# ----------------------------------------------------------

_DB_PATH = os.getenv("SCAN_DB_PATH", "scan_states.db")
_conn: Optional[sqlite3.Connection] = None


# ----------------------------------------------------------
# Connection & Schema Initializer
# ----------------------------------------------------------

def _get_connection() -> sqlite3.Connection:
    """
    Return (or lazily create) the shared SQLite connection.

    check_same_thread=False allows the connection to be used
    across FastAPI worker threads without raising ProgrammingError.

    WAL (Write-Ahead Logging) mode is enabled so concurrent
    reads do not block the single writer — important when
    the frontend polls /scan/{id}/status while a scan is running.
    """
    global _conn

    if _conn is None:
        _conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row

        # WAL mode: readers never block writers, writers never block readers
        _conn.execute("PRAGMA journal_mode=WAL")

        # Create table on first run — no-op on subsequent starts
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS scan_states (
                scan_id         TEXT PRIMARY KEY,
                status          TEXT    NOT NULL DEFAULT 'starting',
                progress        INTEGER NOT NULL DEFAULT 0,
                stage           TEXT             DEFAULT 'initializing',
                stage_detail    TEXT             DEFAULT 'Preparing scan...',
                files_processed INTEGER          DEFAULT 0,
                total_files     INTEGER          DEFAULT 0,
                repo            TEXT,
                result          TEXT
            )
        """)
        _conn.commit()

    return _conn


# ----------------------------------------------------------
# Public API
# (Signatures are identical to the original in-memory version
#  so all callers remain unchanged)
# ----------------------------------------------------------

def create_scan(repo_url: str) -> str:
    """
    Register a new scan in the database and return its scan_id.
    Replaces the previous in-memory dict entry.
    """

    scan_id = str(uuid.uuid4())
    db = _get_connection()

    db.execute(
        """
        INSERT INTO scan_states
            (scan_id, status, progress, stage, stage_detail,
             files_processed, total_files, repo, result)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (scan_id, "starting", 0, "initializing", "Preparing scan...", 0, 0, repo_url, None)
    )
    db.commit()

    return scan_id


def update_scan(
    scan_id: str,
    status: str,
    progress: int,
    stage: Optional[str] = None,
    stage_detail: Optional[str] = None,
    files_processed: Optional[int] = None,
    total_files: Optional[int] = None
):
    """
    Update a scan's progress fields.
    Only non-None arguments are written — keeps the update
    semantics identical to the original dict version.
    """

    db = _get_connection()

    # Build SET clause dynamically from provided arguments
    # so we never accidentally overwrite fields with None
    fields = {"status": status, "progress": progress}

    if stage is not None:
        fields["stage"] = stage
    if stage_detail is not None:
        fields["stage_detail"] = stage_detail
    if files_processed is not None:
        fields["files_processed"] = files_processed
    if total_files is not None:
        fields["total_files"] = total_files

    set_clause = ", ".join(f"{col} = ?" for col in fields)
    values = list(fields.values()) + [scan_id]

    db.execute(
        f"UPDATE scan_states SET {set_clause} WHERE scan_id = ?",
        values
    )
    db.commit()


def complete_scan(scan_id: str, result):
    """
    Mark a scan as complete and persist the full result payload.
    The result object is serialized to JSON text for storage.
    """

    db = _get_connection()

    # Serialize result to JSON — handles dicts, lists, and None
    result_json = json.dumps(result, default=str) if result is not None else None

    db.execute(
        """
        UPDATE scan_states
        SET status       = 'complete',
            progress     = 100,
            stage        = 'complete',
            stage_detail = 'Scan complete',
            result       = ?
        WHERE scan_id = ?
        """,
        (result_json, scan_id)
    )
    db.commit()


def get_scan(scan_id: str) -> Optional[Dict]:
    """
    Retrieve a scan state by ID.
    Returns a plain dict (same shape as the original in-memory
    dict entries) or None if the scan_id does not exist.
    """

    db = _get_connection()

    row = db.execute(
        "SELECT * FROM scan_states WHERE scan_id = ?",
        (scan_id,)
    ).fetchone()

    if row is None:
        return None

    # Deserialize JSON result back to its original type
    result_raw = row["result"]
    result = json.loads(result_raw) if result_raw else None

    return {
        "status":          row["status"],
        "progress":        row["progress"],
        "stage":           row["stage"],
        "stage_detail":    row["stage_detail"],
        "files_processed": row["files_processed"],
        "total_files":     row["total_files"],
        "repo":            row["repo"],
        "result":          result,
    }