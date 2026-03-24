# ==========================================================
# File: dependency_graph.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Builds a dependency graph between repository files
# based on their import statements.
#
# Example Output
# ----------------------------------------------------------
# {
#     "model.py": ["numpy", "utils"],
#     "trainer.py": ["model", "data_loader"]
# }
#
# This graph helps the repository analysis system:
# • understand module dependencies
# • identify tightly coupled files
# • provide context for AI code review and RAG retrieval
# ==========================================================

from collections import defaultdict
from typing import Dict, List


# ==========================================================
# Build Repository Dependency Graph
# ==========================================================
def build_dependency_graph(files_data: List[Dict]) -> Dict[str, List[str]]:
    """
    Build dependency relationships between repository files.

    Parameters
    ----------
    files_data : List[Dict]
        Repository file metadata containing:
        {
            "file_name": str,
            "imports": List[str]
        }

    Returns
    -------
    Dict[str, List[str]]
        Mapping of file name → imported modules
    """

    graph: Dict[str, List[str]] = defaultdict(list)

    for file in files_data:

        file_name = file.get("file_name")
        imports = file.get("imports", [])

        if not file_name:
            continue

        for imp in imports:

            if imp is None:
                continue

            graph[file_name].append(imp)

        # Remove duplicates while preserving order
        graph[file_name] = list(dict.fromkeys(graph[file_name]))

    return dict(graph)