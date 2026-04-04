# ==========================================================
# File: llm_refactor_engine.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# This module generates AI-assisted refactoring suggestions
# based on the results of the repository analysis pipeline.
#
# It combines:
# • Static analysis metrics
# • Code smell detection
# • Heuristic-based improvements (docstrings, type hints)
#
# The engine produces:
# • explanations
# • suggested improvements
# • improved code (when heuristic rules apply)
# • a diff patch representing the changes
# ==========================================================

import ast
import re
from typing import Dict, Any, List
from backend.app.analysis.patch_generator import PatchGenerator


class LLMRefactorEngine:
    """
    Orchestrates AI-assisted code refactoring based on
    repository analysis results.
    """

    # ======================================================
    # Initialization
    # ======================================================

    def __init__(self):
        self.patch_generator = PatchGenerator()

    # ======================================================
    # Heuristic Code Improvement
    # ======================================================

    def _add_missing_docstrings(self, code: str) -> str:
        """
        Add placeholder docstrings to functions/classes
        that don't have them.
        """

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code

        lines = code.splitlines(True)
        insertions = []  # (line_number, indent, name, kind)

        for node in ast.walk(tree):

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):

                kind = "function"
                name = node.name

                # Check if already has docstring
                has_docstring = (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                )

                if not has_docstring and node.body:

                    # Get indentation of function body
                    first_body_line = node.body[0].lineno - 1
                    if first_body_line < len(lines):
                        body_line = lines[first_body_line]
                        indent = len(body_line) - len(body_line.lstrip())
                    else:
                        indent = (node.col_offset or 0) + 4

                    # Get parameters for docstring
                    params = []
                    for arg in node.args.args:
                        if arg.arg != "self" and arg.arg != "cls":
                            params.append(arg.arg)

                    insertions.append((first_body_line, indent, name, kind, params))

            elif isinstance(node, ast.ClassDef):

                has_docstring = (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                )

                if not has_docstring and node.body:
                    first_body_line = node.body[0].lineno - 1
                    if first_body_line < len(lines):
                        body_line = lines[first_body_line]
                        indent = len(body_line) - len(body_line.lstrip())
                    else:
                        indent = (node.col_offset or 0) + 4

                    insertions.append((first_body_line, indent, node.name, "class", []))

        if not insertions:
            return code

        # Sort insertions in reverse order to maintain line numbers
        insertions.sort(key=lambda x: x[0], reverse=True)

        for line_num, indent, name, kind, params in insertions:
            indent_str = " " * indent

            if kind == "class":
                docstring = f'{indent_str}"""Class {name}."""\n'
            elif params:
                param_docs = "\n".join(f"{indent_str}    {p}: Description." for p in params)
                docstring = (
                    f'{indent_str}"""\n'
                    f'{indent_str}{name.replace("_", " ").capitalize()}.\n'
                    f'\n'
                    f'{indent_str}Args:\n'
                    f'{param_docs}\n'
                    f'{indent_str}"""\n'
                )
            else:
                docstring = f'{indent_str}"""{name.replace("_", " ").capitalize()}."""\n'

            lines.insert(line_num, docstring)

        return "".join(lines)

    def _add_type_hints_to_simple_functions(self, code: str) -> str:
        """
        Add return type hints to simple functions that lack them.
        Very conservative — only adds -> None for functions
        with no return statement.
        """

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code

        lines = code.splitlines()
        modifications = []

        for node in ast.walk(tree):

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):

                # Skip if already has return annotation
                if node.returns is not None:
                    continue

                # Check if function has any return with value
                has_return_value = False
                for child in ast.walk(node):
                    if isinstance(child, ast.Return) and child.value is not None:
                        has_return_value = True
                        break

                if not has_return_value:
                    # Find the def line
                    def_line = node.lineno - 1
                    if def_line < len(lines):
                        line = lines[def_line]
                        # Add -> None before the colon
                        if "):" in line and "-> " not in line:
                            modifications.append((def_line, "):", ") -> None:"))

        # Apply modifications in reverse order
        modifications.sort(key=lambda x: x[0], reverse=True)

        for line_num, old, new in modifications:
            lines[line_num] = lines[line_num].replace(old, new, 1)

        return "\n".join(lines)

    # ======================================================
    # Main Refactor Function
    # ======================================================

    def generate_refactor(
        self,
        code: str,
        analysis_result: Dict[str, Any],
        complexity: Dict[str, Any],
        smells: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate AI-assisted refactoring suggestions.
        """

        # --------------------------------------------------
        # Safely extract analysis information
        # --------------------------------------------------

        analysis = analysis_result.get("analysis", {})

        explanation = analysis.get("explanation", "")
        suggestions = list(analysis.get("suggestions", []))

        improved_code = code  # Start with original

        # --------------------------------------------------
        # Apply heuristic improvements
        # --------------------------------------------------

        # Add docstrings to undocumented functions
        improved_code = self._add_missing_docstrings(improved_code)

        # Add type hints to simple functions
        improved_code = self._add_type_hints_to_simple_functions(improved_code)

        # --------------------------------------------------
        # Complexity-based suggestions
        # --------------------------------------------------

        if complexity.get("max_loop_depth", 0) >= 3:
            suggestions.append(
                "Consider reducing nested loops using sets, "
                "dictionary lookups, or vectorized operations."
            )

        if complexity.get("cyclomatic_complexity", 0) > 10:
            suggestions.append(
                "Function complexity is high. Consider breaking "
                "the function into smaller helper functions."
            )

        # --------------------------------------------------
        # Handle smell formats safely
        # --------------------------------------------------

        smell_list = []

        if isinstance(smells, dict):
            smell_list = smells.get("code_smells", [])
        elif isinstance(smells, list):
            smell_list = smells

        if smell_list:
            suggestions.append(
                "Code smells detected. Consider refactoring for better readability "
                "and maintainability."
            )

        # --------------------------------------------------
        # Generate explanation about what was improved
        # --------------------------------------------------

        if improved_code != code:
            changes = []
            orig_lines = code.splitlines()
            impr_lines = improved_code.splitlines()

            added_docstrings = sum(1 for l in impr_lines if '"""' in l) - sum(1 for l in orig_lines if '"""' in l)
            added_hints = sum(1 for l in impr_lines if '-> None:' in l) - sum(1 for l in orig_lines if '-> None:' in l)

            if added_docstrings > 0:
                changes.append(f"Added docstrings to {added_docstrings // 2} undocumented function(s)/class(es)")
            if added_hints > 0:
                changes.append(f"Added return type hints to {added_hints} function(s)")

            if changes:
                improvement_desc = ". ".join(changes) + "."
                explanation = f"{explanation}\n\n**Suggested improvements (unapplied):** {improvement_desc}"

        # --------------------------------------------------
        # Generate patch only if code changed
        # --------------------------------------------------

        patch = None

        if improved_code != code:
            patch = self.patch_generator.generate_patch(code, improved_code)

        return {
            "explanation": explanation,
            "suggestions": suggestions,
            "improved_code": improved_code,
            "patch": patch
        }