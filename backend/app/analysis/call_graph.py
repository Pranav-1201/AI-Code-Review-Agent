import ast
from collections import defaultdict


def extract_function_calls(code):
    """
    Extract function calls inside a single file.
    """

    tree = ast.parse(code)

    calls = []

    for node in ast.walk(tree):

        if isinstance(node, ast.Call):

            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)

            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)

    return calls


def build_call_graph(files_data):
    """
    Build a repository-wide call graph.
    """

    graph = defaultdict(list)

    for file in files_data:

        file_name = file["file_name"]
        code = file["content"]

        calls = extract_function_calls(code)

        graph[file_name].extend(calls)

    return graph