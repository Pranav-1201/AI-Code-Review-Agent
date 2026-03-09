from pydantic import BaseModel
from typing import List


class Issue(BaseModel):
    file_path: str
    issue_type: str
    severity: str
    description: str
    suggestion: str


class ReviewReport(BaseModel):
    repo_name: str
    commit_id: str
    score: float
    summary: str
    issues: List[Issue]
    