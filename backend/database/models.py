# ==========================================================
# File: models.py
# Purpose: Pydantic data models for review reports
# ==========================================================

from pydantic import BaseModel, Field
from typing import List, Optional


# ----------------------------------------------------------
# Issue Model
# ----------------------------------------------------------

class Issue(BaseModel):
    """
    Represents a single code issue detected during analysis.
    """

    file_path: str
    issue_type: str
    severity: str = Field(
        default="MEDIUM",
        description="Severity level: LOW, MEDIUM, HIGH"
    )
    description: str
    suggestion: Optional[str] = None


# ----------------------------------------------------------
# Review Report Model
# ----------------------------------------------------------

class ReviewReport(BaseModel):
    """
    Structured review report for a repository analysis.
    """

    repo_name: str
    commit_id: str
    score: float
    summary: str

    issues: List[Issue] = []

    # Optional extended metadata
    security_risks: Optional[List[str]] = None
    complexity_metrics: Optional[dict] = None
    code_smells: Optional[List[str]] = None