# ==========================================================
# File: patch_generator.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Generates a unified diff patch between two versions of
# source code.
#
# The patch format follows the standard "unified diff"
# format used by tools like:
# • Git
# • GitHub Pull Requests
# • Linux patch utility
#
# This allows the AI refactor engine to produce machine-
# readable code modifications.
# ==========================================================

import difflib
from typing import Optional


class PatchGenerator:
    """
    Utility class responsible for generating diff patches
    between original and improved code versions.
    """

    # ======================================================
    # Generate Unified Diff Patch
    # ======================================================

    def generate_patch(
        self,
        original_code: str,
        improved_code: str
    ) -> Optional[str]:
        """
        Generate a unified diff patch.

        Parameters
        ----------
        original_code : str
            Original source code.

        improved_code : str
            Refactored or improved source code.

        Returns
        -------
        Optional[str]
            Unified diff patch string or None if no changes.
        """

        # If code is identical, no patch is needed
        if original_code == improved_code:
            return None

        original_lines = original_code.splitlines()
        improved_lines = improved_code.splitlines()

        diff = difflib.unified_diff(
            original_lines,
            improved_lines,
            fromfile="original",
            tofile="improved",
            lineterm=""
        )

        patch = "\n".join(diff)

        return patch if patch else None