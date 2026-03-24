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
from typing import Optional, Tuple


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
        improved_code: str,
        filename: str = "file.py",
        context_lines: int = 3
    ) -> Optional[str]:
        """
        Generate a unified diff patch.

        Parameters
        ----------
        original_code : str
            Original source code.

        improved_code : str
            Refactored or improved source code.

        filename : str
            Name of the file being patched (used in headers).

        context_lines : int
            Number of context lines to include around changes.

        Returns
        -------
        Optional[str]
            Unified diff patch string or None if no changes.
        """

        # --------------------------------------------------
        # Normalize line endings to avoid false diffs
        # --------------------------------------------------

        if original_code is None:
            original_code = ""

        if improved_code is None:
            improved_code = ""

        original_code = original_code.replace("\r\n", "\n")
        improved_code = improved_code.replace("\r\n", "\n")

        # If code is identical, no patch is needed
        if original_code == improved_code:
            return None

        original_lines = original_code.splitlines()
        improved_lines = improved_code.splitlines()

        # --------------------------------------------------
        # Generate unified diff
        # --------------------------------------------------

        diff = difflib.unified_diff(
            original_lines,
            improved_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            n=context_lines,
            lineterm=""
        )

        patch = "\n".join(diff)

        return patch if patch else None

    # ======================================================
    # Patch Statistics (Optional Utility)
    # ======================================================

    def patch_stats(self, patch: str) -> Tuple[int, int]:
        """
        Calculate number of added and removed lines in patch.

        Returns
        -------
        Tuple[int, int]
            (added_lines, removed_lines)
        """

        added = 0
        removed = 0

        if not patch:
            return (0, 0)

        for line in patch.splitlines():

            if line.startswith("+") and not line.startswith("+++"):
                added += 1

            elif line.startswith("-") and not line.startswith("---"):
                removed += 1

        return added, removed