# ==========================================================
# File: refactoring_engine.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Rule-based refactoring suggestion engine.
#
# This module generates deterministic code improvement
# suggestions based on:
#
# • complexity metrics
# • detected code smells
#
# Unlike the LLM refactor engine, this component does not
# rely on AI and provides explainable recommendations.
# ==========================================================

from typing import Dict, List, Optional
from app.analysis.patch_generator import PatchGenerator


class RefactoringEngine:
    """
    Generates rule-based refactoring suggestions and patches.
    """

    # ======================================================
    # Initialization
    # ======================================================

    def __init__(self):
        self.patch_generator = PatchGenerator()

    # ======================================================
    # Generate Patch Suggestion
    # ======================================================

    def generate_patch_suggestion(
        self,
        original_code: str,
        improved_code: str
    ) -> Dict[str, Optional[str]]:
        """
        Generate a patch suggestion between original and improved code.
        """

        patch = None

        if original_code != improved_code:
            patch = self.patch_generator.generate_patch(
                original_code,
                improved_code
            )

        return {
            "improved_code": improved_code,
            "patch": patch
        }

    # ======================================================
    # Generate Refactoring Suggestions
    # ======================================================

    def generate_suggestions(
        self,
        complexity: Dict,
        smells: Dict
    ) -> List[str]:
        """
        Generate rule-based improvement suggestions based
        on static analysis results.
        """

        suggestions = []

        cyclomatic = complexity.get("cyclomatic_complexity", 0)
        loop_depth = complexity.get("max_loop_depth", 0)
        recursive = complexity.get("recursive", False)

        # --------------------------------------------------
        # Complexity Based Suggestions
        # --------------------------------------------------

        if cyclomatic > 10:
            suggestions.append(
                "Function has high cyclomatic complexity. "
                "Consider splitting it into smaller functions."
            )

        if loop_depth >= 3:
            suggestions.append(
                "Deep loop nesting detected. Consider using "
                "hash maps, sets, or preprocessing techniques "
                "instead of nested loops."
            )

        if recursive:
            suggestions.append(
                "Recursive function detected. Consider "
                "memoization or dynamic programming if "
                "performance is critical."
            )

        # --------------------------------------------------
        # Code Smell Suggestions
        # --------------------------------------------------

        for smell in smells.get("code_smells", []):

            if smell == "Long Function":
                suggestions.append(
                    "Function is too long. Break it into "
                    "smaller reusable functions."
                )

            elif smell == "Deep Nesting":
                suggestions.append(
                    "Deep nesting detected. Refactor using "
                    "guard clauses or helper functions."
                )

            elif smell == "Magic Numbers":
                suggestions.append(
                    "Magic numbers detected. Replace them "
                    "with named constants."
                )

            elif smell == "God Function":
                suggestions.append(
                    "Function violates the Single "
                    "Responsibility Principle."
                )

        # --------------------------------------------------
        # Remove duplicate suggestions
        # --------------------------------------------------

        suggestions = list(dict.fromkeys(suggestions))

        return suggestions