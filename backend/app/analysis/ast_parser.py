import ast


def parse_python_file(code: str):
    """
    Extract functions and imports from a Python file using AST.
    """

    tree = ast.parse(code)

    functions = []
    imports = []

    for node in ast.walk(tree):

        if isinstance(node, ast.FunctionDef):
            functions.append(node.name)

        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module)

    return {
        "functions": functions,
        "imports": imports
    }