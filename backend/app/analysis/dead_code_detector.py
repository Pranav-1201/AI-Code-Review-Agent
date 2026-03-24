import ast


class DeadCodeDetector:

    def analyze(self, code: str):

        tree = ast.parse(code)

        imports = []
        functions = []
        assigned_vars = []
        used_names = set()

        for node in ast.walk(tree):

            # detect imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)

            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imports.append(alias.name)

            # detect function definitions
            if isinstance(node, ast.FunctionDef):
                functions.append(node.name)

            # detect variable assignments
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned_vars.append(target.id)

            # detect variable usage
            if isinstance(node, ast.Name):
                used_names.add(node.id)

        unused_imports = [i for i in imports if i not in used_names]
        unused_variables = [v for v in assigned_vars if v not in used_names]

        # NOTE: unused_functions will be finalized later using call graph
        return {
            "imports": imports,
            "functions": functions,
            "unused_imports": unused_imports,
            "unused_variables": unused_variables
        }

    def detect_repository_dead_functions(self, files_data, call_graph):

        defined_functions = set()
        called_functions = set()

        for file in files_data:
            defined_functions.update(file["functions"])

        for file_calls in call_graph.values():
            called_functions.update(file_calls)

        unused_functions = list(defined_functions - called_functions)

        return unused_functions