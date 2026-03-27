# ==========================================================
# File: dependency_graph.py
# Location: backend/app/analysis
#
# Purpose
# ----------------------------------------------------------
# Builds a dependency graph between repository files
# based on their import statements.
#
# Output format (for frontend graph visualization):
#
# {
#     "nodes": [
#         {"id": "model.py"},
#         {"id": "trainer.py"}
#     ],
#     "links": [
#         {"source": "trainer.py", "target": "model.py"}
#     ]
# }
# ==========================================================

from typing import Dict, List, Any


# ==========================================================
# Build Repository Dependency Graph
# ==========================================================

def build_dependency_graph(files_data: List[Dict]) -> Dict[str, Any]:
    """
    Build dependency graph between repository files.

    Parameters
    ----------
    files_data : List[Dict]

    Example input:
    [
        {
            "file_name": "trainer.py",
            "imports": ["model", "utils"]
        }
    ]

    Returns
    -------
    Dict containing nodes and links
    """

    nodes = []
    links = []

    seen_nodes = set()

    for file in files_data:

        file_name = file.get("file_name")
        imports = file.get("imports", [])

        if not file_name:
            continue

        # Add node for file
        if file_name not in seen_nodes:
            nodes.append({"id": file_name})
            seen_nodes.add(file_name)

        for imp in imports:

            if not imp:
                continue

            # Add node for dependency
            if imp not in seen_nodes:
                nodes.append({"id": imp})
                seen_nodes.add(imp)

            # Add edge
            links.append({
                "source": file_name,
                "target": imp
            })

    return {
        "nodes": nodes,
        "links": links
    }