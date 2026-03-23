import ast


def extract_function_calls(code):

    tree = ast.parse(code)

    calls = []

    for node in ast.walk(tree):

        if isinstance(node, ast.Call):

            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)

            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)

    return calls