from collections import defaultdict


def build_dependency_graph(files_data):
    """
    Build dependency graph between repository files.
    """

    graph = defaultdict(list)

    for file in files_data:

        file_name = file["file_name"]
        imports = file.get("imports", [])

        for imp in imports:
            graph[file_name].append(imp)

    return graph