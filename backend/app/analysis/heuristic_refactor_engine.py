# ==========================================================
# File: heuristic_refactor_engine.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Deterministic, HEURISTIC refactoring suggestions from the
# repository analysis pipeline. Renamed from LLMRefactorEngine
# (Phase 5): the old name was a misnomer — there is no LLM here.
# This engine applies rule-based AST transforms (placeholder
# docstrings, `-> None` hints) and complexity/smell-driven
# suggestion strings, then emits a diff patch. Natural-language
# reasoning lives in the separate Anthropic explanation layer
# (services/explanation_engine.py).
#
# It combines:
# • Static analysis metrics
# • Code smell detection
# • Heuristic-based improvements (docstrings, type hints)
#
# The engine produces:
# • suggested improvements
# • improved code (when heuristic rules apply)
# • a diff patch representing the changes
# ==========================================================

import ast
import re
from typing import Dict, Any, List, Tuple
from backend.app.analysis.patch_generator import PatchGenerator


class HeuristicRefactorEngine:
    """
    Applies deterministic, rule-based refactoring transforms and
    suggestions from repository analysis results. No LLM involved
    (see explanation_engine.py for the genuine LLM layer).
    """

    # ======================================================
    # Initialization
    # ======================================================

    def __init__(self):
        self.patch_generator = PatchGenerator()

    # ======================================================
    # Heuristic Code Improvement
    # ======================================================

    def _add_missing_docstrings(self, code: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Add placeholder docstrings to functions/classes
        that don't have them.
        """

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code, []

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
            return code, []

        # Insert ASCENDING and carry two counters. `elements_added` tracks list
        # positions (each insertion adds one element, however many lines it
        # holds); `lines_added` tracks rendered lines, which is what a line
        # number in the improved file means. Conflating them puts a multi-line
        # docstring's own body into the next change's line number.
        insertions.sort(key=lambda x: x[0])

        changes: List[Dict[str, Any]] = []
        elements_added = 0
        lines_added = 0

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

            lines.insert(line_num + elements_added, docstring)

            line_count = docstring.count("\n")

            changes.append({
                "kind": "docstring",
                "target": "class" if kind == "class" else "function",
                "name": name,
                "line": line_num + lines_added + 1,
                "line_count": line_count,
            })

            elements_added += 1
            lines_added += line_count

        return "".join(lines), changes

    def _add_type_hints_to_simple_functions(self, code: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Add return type hints to simple functions that lack them.
        Very conservative — only adds -> None for functions
        with no return statement.
        """

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code, []

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
                            modifications.append((def_line, node.name, "):", ") -> None:"))

        # This pass re-parses the already-docstringed code, so `def_line` is
        # already an improved-file coordinate, and replacing in place changes
        # no line count -- these records need no offset and do not invalidate
        # the docstring records computed before them.
        modifications.sort(key=lambda x: x[0], reverse=True)

        changes: List[Dict[str, Any]] = []

        for line_num, name, old, new in modifications:
            lines[line_num] = lines[line_num].replace(old, new, 1)
            changes.append({
                "kind": "return_hint",
                "target": "function",
                "name": name,
                "line": line_num + 1,
                "line_count": 1,
            })

        changes.sort(key=lambda c: c["line"])

        return "\n".join(lines), changes

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
        improved_code, docstring_changes = self._add_missing_docstrings(improved_code)

        # Add type hints to simple functions
        improved_code, hint_changes = self._add_type_hints_to_simple_functions(improved_code)

        changes = docstring_changes + hint_changes

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

        # The summary is built from the change list, not by counting `"""`
        # lines. The old arithmetic divided that count by two, which assumed
        # every docstring spanned two lines -- but classes and parameterless
        # functions get a single-line docstring, so a file whose only gaps were
        # those reported "to 0" while the pane beside it showed the insertions.
        if changes:
            doc_functions = sum(
                1 for c in changes if c["kind"] == "docstring" and c["target"] == "function"
            )
            doc_classes = sum(
                1 for c in changes if c["kind"] == "docstring" and c["target"] == "class"
            )
            hint_count = sum(1 for c in changes if c["kind"] == "return_hint")

            parts = []

            if doc_functions or doc_classes:
                targets = []
                if doc_functions:
                    targets.append(f"{doc_functions} function" + ("" if doc_functions == 1 else "s"))
                if doc_classes:
                    targets.append(f"{doc_classes} class" + ("" if doc_classes == 1 else "es"))
                parts.append("Added placeholder docstrings to " + " and ".join(targets))

            if hint_count:
                parts.append(
                    f"Added `-> None` return hints to {hint_count} function"
                    + ("" if hint_count == 1 else "s")
                )

            improvement_desc = ". ".join(parts) + "."
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
            "patch": patch,
            "changes": changes
        }