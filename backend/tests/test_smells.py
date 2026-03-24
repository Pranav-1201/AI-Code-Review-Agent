import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ast
from app.analysis.code_smell_detector import CodeSmellDetector

code = """
def process_data(arr):
    total = 0
    for i in arr:
        for j in arr:
            for k in arr:
                if i == j:
                    if j == k:
                        total += 42
    return total
"""

tree = ast.parse(code)

detector = CodeSmellDetector()

for node in ast.walk(tree):

    if isinstance(node, ast.FunctionDef):

        result = detector.analyze_function(node)

        print(node.name)
        print(result)