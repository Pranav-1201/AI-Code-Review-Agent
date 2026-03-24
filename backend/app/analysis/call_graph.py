# ==========================================================
# File: call_graph.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Builds a function call graph for a repository by analyzing
# Python source code using AST.
#
# The call graph represents which functions are invoked
# inside each file.
#
# Example Output
# ----------------------------------------------------------
# {
#     "utils.py": ["load_data", "process_data"],
#     "model.py": ["predict", "numpy"]
# }
#
# This structure helps the AI analysis system understand
# dependencies between components before performing
# embedding, RAG retrieval, or code review.
# ==========================================================

import ast
from collections import defaultdict
from typing import Dict, List


# ==========================================================
# Function Call Extraction
# ==========================================================
def extract_function_calls(code: str) -> List[str]:
    """
    Extract all function calls from a single Python file.

    Parameters
    ----------
    code : str
        Python source code.

    Returns
    -------
    List[str]
        List of called function names.
    """

    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Prevent crash if file has invalid syntax
        return []

    calls: List[str] = []

    # Walk through AST nodes
    for node in ast.walk(tree):

        if isinstance(node, ast.Call):

            # Example: foo()
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)

            # Example: obj.method()
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)

    # Remove duplicates while preserving order
    calls = list(dict.fromkeys(calls))

    return calls


# ==========================================================
# Repository-Level Call Graph Builder
# ==========================================================
def build_call_graph(files_data: List[Dict]) -> Dict[str, List[str]]:
    """
    Construct a call graph for an entire repository.

    Parameters
    ----------
    files_data : List[Dict]
        List containing repository file data.
        Each item must contain:
        {
            "file_name": str,
            "content": str
        }

    Returns
    -------
    Dict[str, List[str]]
        Mapping of file name → functions called in that file.
    """

    graph: Dict[str, List[str]] = defaultdict(list)

    for file in files_data:

        file_name = file.get("file_name")
        code = file.get("content", "")

        calls = extract_function_calls(code)

        graph[file_name].extend(calls)

    return dict(graph)