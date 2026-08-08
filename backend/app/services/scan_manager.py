# ==========================================================
# File: scan_manager.py
# Purpose: Track repository scan progress with stage details
# Persistence: SQLite (survives process restarts)
# ==========================================================

import os
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


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

# A scan is "done" only in one of these states. Everything else
# (starting / cloning / analyzing / finalizing) is in-flight and, if seen
# at process startup, is a zombie left by a killed previous process.
_TERMINAL_STATUSES = ("complete", "error")


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
                result          TEXT,
                created_at      TEXT
            )
        """)

        # Migration: databases created before scan-history (Fix K) lack
        # created_at. Add it in place; a duplicate-column error just means a
        # fresh DB already has it. Additive and idempotent across restarts.
        try:
            _conn.execute("ALTER TABLE scan_states ADD COLUMN created_at TEXT")
        except sqlite3.OperationalError:
            pass

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
    created_at = datetime.now(timezone.utc).isoformat()
    db = _get_connection()

    db.execute(
        """
        INSERT INTO scan_states
            (scan_id, status, progress, stage, stage_detail,
             files_processed, total_files, repo, result, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (scan_id, "starting", 0, "initializing", "Preparing scan...",
         0, 0, repo_url, None, created_at)
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

    # A scan that finished with an error is terminal too, but it must be
    # distinguishable from success. Emit status='error' (which the frontend
    # poller already treats as a terminal failure and reads `status.error`
    # from) instead of masquerading as 'complete'. Restart-interrupted scans
    # use the same terminal state via recover_interrupted_scans().
    is_error = isinstance(result, dict) and bool(result.get("error"))
    status = "error" if is_error else "complete"
    stage_detail = "Scan failed" if is_error else "Scan complete"

    db.execute(
        """
        UPDATE scan_states
        SET status       = ?,
            progress     = 100,
            stage        = ?,
            stage_detail = ?,
            result       = ?
        WHERE scan_id = ?
        """,
        (status, status, stage_detail, result_json, scan_id)
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

    out = {
        "status":          row["status"],
        "progress":        row["progress"],
        "stage":           row["stage"],
        "stage_detail":    row["stage_detail"],
        "files_processed": row["files_processed"],
        "total_files":     row["total_files"],
        "repo":            row["repo"],
        "result":          result,
    }

    # Surface a top-level error message for terminal-failure scans so the
    # frontend poller (which reads `status.error`) shows the real reason
    # instead of "unknown reason". Additive — present only on failed scans.
    if isinstance(result, dict) and result.get("error"):
        out["error"] = result["error"]

    return out


def list_scans(limit: int = 50) -> List[Dict]:
    """Return recent COMPLETED scans as compact history rows (Fix K).

    Powers the frontend Scan History page so history survives a page reload
    instead of living only in browser memory. Only status='complete' scans are
    listed — they carry a full result payload to summarise; in-flight and
    errored scans are omitted. health_score/files_analyzed come from the stored
    result's repository_summary and issues_found is summed across file_reports;
    a malformed or legacy row degrades to zeros rather than failing the list.
    Ordered newest-first by created_at (NULLs from pre-migration rows sort last).
    """
    db = _get_connection()

    rows = db.execute(
        """
        SELECT scan_id, repo, created_at, result
        FROM scan_states
        WHERE status = 'complete'
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    history: List[Dict] = []
    for row in rows:
        summary: Dict = {}
        issues_found = 0
        try:
            result = json.loads(row["result"]) if row["result"] else {}
            summary = result.get("repository_summary") or result.get("summary") or {}
            for report in (result.get("file_reports") or result.get("reports") or []):
                issues_found += len(report.get("issues") or [])
        except (json.JSONDecodeError, TypeError, AttributeError):
            summary = {}

        history.append({
            "id":             row["scan_id"],
            "repo":           row["repo"],
            "timestamp":      row["created_at"],
            "health_score":   summary.get("health_score", 0),
            "files_analyzed": summary.get("files_analyzed", summary.get("files", 0)),
            "issues_found":   issues_found,
        })

    return history


# ----------------------------------------------------------
# Zombie-scan recovery (Phase 6 / Chunk 5)
# ----------------------------------------------------------

def recover_interrupted_scans() -> int:
    """Reconcile scans left mid-flight by a previous process.

    Scan work runs in-process (FastAPI BackgroundTasks today), so any scan
    still in a running state at startup was killed together with the
    previous process — its task cannot resume. Without this, such a row
    stays 'analyzing' forever and the UI polls a dead scan until its
    client-side deadline.

    We mark every non-terminal row terminal as status='error' with a clear
    message (the frontend poller already treats 'error' as a terminal
    failure). Terminal rows ('complete'/'error') are left untouched, so
    calling this is idempotent. Returns the number of scans reconciled.
    """
    db = _get_connection()
    placeholders = ",".join("?" for _ in _TERMINAL_STATUSES)

    rows = db.execute(
        f"SELECT scan_id FROM scan_states WHERE status NOT IN ({placeholders})",
        _TERMINAL_STATUSES,
    ).fetchall()
    if not rows:
        return 0

    result_json = json.dumps(
        {"error": "Scan interrupted by a server restart before it finished."}
    )
    db.execute(
        f"""
        UPDATE scan_states
        SET status       = 'error',
            stage        = 'interrupted',
            stage_detail = 'Scan interrupted by a server restart',
            result       = ?
        WHERE status NOT IN ({placeholders})
        """,
        (result_json, *_TERMINAL_STATUSES),
    )
    db.commit()
    return len(rows)