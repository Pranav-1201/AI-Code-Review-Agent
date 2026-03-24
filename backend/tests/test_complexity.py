import ast
from app.analysis.complexity_analyzer import ComplexityAnalyzer

code = """
def example(arr):
    for i in arr:
        for j in arr:
            if i == j:
                print(i)
"""

tree = ast.parse(code)

analyzer = ComplexityAnalyzer()

for node in ast.walk(tree):

    if isinstance(node, ast.FunctionDef):

        result = analyzer.analyze_function(node)

        print(node.name)
        print(result)