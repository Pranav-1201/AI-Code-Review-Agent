# ==========================================================
# File: scan_manager.py
# Purpose: Track repository scan progress with stage details
# ==========================================================

from typing import Dict, Optional
import uuid

SCAN_STATES: Dict[str, Dict] = {}


def create_scan(repo_url: str):

    scan_id = str(uuid.uuid4())

    SCAN_STATES[scan_id] = {
        "status": "starting",
        "progress": 0,
        "stage": "initializing",
        "stage_detail": "Preparing scan...",
        "files_processed": 0,
        "total_files": 0,
        "repo": repo_url,
        "result": None
    }

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

    if scan_id in SCAN_STATES:
        SCAN_STATES[scan_id]["status"] = status
        SCAN_STATES[scan_id]["progress"] = progress

        if stage is not None:
            SCAN_STATES[scan_id]["stage"] = stage
        if stage_detail is not None:
            SCAN_STATES[scan_id]["stage_detail"] = stage_detail
        if files_processed is not None:
            SCAN_STATES[scan_id]["files_processed"] = files_processed
        if total_files is not None:
            SCAN_STATES[scan_id]["total_files"] = total_files


def complete_scan(scan_id: str, result):

    if scan_id in SCAN_STATES:
        SCAN_STATES[scan_id]["status"] = "complete"
        SCAN_STATES[scan_id]["progress"] = 100
        SCAN_STATES[scan_id]["stage"] = "complete"
        SCAN_STATES[scan_id]["stage_detail"] = "Scan complete"
        SCAN_STATES[scan_id]["result"] = result


def get_scan(scan_id: str):

    return SCAN_STATES.get(scan_id)