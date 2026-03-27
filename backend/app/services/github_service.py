# ==========================================================
# File: github_service.py
# Purpose: Interact with GitHub API
# ==========================================================

import requests
import os

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}


def get_pr_files(repo_full_name, pr_number):

    url = f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}/files"

    response = requests.get(url, headers=HEADERS)

    response.raise_for_status()

    return response.json()


def post_pr_comment(repo_full_name, pr_number, body):

    url = f"https://api.github.com/repos/{repo_full_name}/issues/{pr_number}/comments"

    response = requests.post(
        url,
        headers=HEADERS,
        json={"body": body}
    )

    response.raise_for_status()

    return response.json()