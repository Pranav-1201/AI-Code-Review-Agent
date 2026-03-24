import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.append(project_root)
sys.path.append(os.path.join(project_root, "backend"))

from app.services.repository_review_engine import RepositoryReviewEngine


repo_path = "backend/tests/sample_repo"

engine = RepositoryReviewEngine()

result = engine.review_repository(repo_path)

print("\nRepository Summary\n")
print(result["repository_summary"])

print("\nFile Reports\n")
for report in result["file_reports"]:
    print(report)