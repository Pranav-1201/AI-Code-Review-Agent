# ==========================================================
# File: pr_review_engine.py
# Purpose: Run AI code review on PR files
# ==========================================================

from backend.app.services.github_service import get_pr_files, post_pr_comment
from backend.app.services.repository_review_engine import analyze_single_file
from backend.app.analysis.llm_refactor_engine import LLMRefactorEngine


def review_pull_request(repo, pr_number):

    files = get_pr_files(repo, pr_number)

    refactor_engine = LLMRefactorEngine()

    comments = []

    for file in files:

        if not file["filename"].endswith(".py"):
            continue

        patch = file.get("patch", "")

        file_data = {
            "content": patch,
            "file_name": file["filename"]
        }

        result = analyze_single_file(file_data, refactor_engine)

        if result["issues"]:

            issue_text = "\n".join(
                f"- {i['message']}" for i in result["issues"]
            )

            comment = f"""
### 🤖 AI Code Review

File: `{file["filename"]}`

Issues detected:
{issue_text}

Suggested Refactor:
{result.get("refactor_suggestion", "No refactor suggestion")}
"""

            comments.append(comment)

    # ------------------------------------------------------
    # Post comments to PR
    # ------------------------------------------------------

    for comment in comments:
        post_pr_comment(repo, pr_number, comment)