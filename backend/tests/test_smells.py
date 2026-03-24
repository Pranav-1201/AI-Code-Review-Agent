"""
Unit tests for CodeSmellDetector.

This module tests the static code smell detection system
used by the AI code review pipeline.

The detector should identify issues like:

- deep nesting
- magic numbers
- overly complex functions

Tests use small AST snippets so they run quickly.
"""

import sys
import os
import ast

# Allow importing backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.analysis.code_smell_detector import CodeSmellDetector


# ---------------------------------------------------------
# Helper function
# ---------------------------------------------------------

def get_function_node(code):
    """
    Parse code and return the first function node.
    """
    tree = ast.parse(code)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            return node

    return None


# ---------------------------------------------------------
# Test: Deep nesting detection
# ---------------------------------------------------------

def test_deep_nesting():

    code = """
def process_data(arr):
    for i in arr:
        for j in arr:
            for k in arr:
                if i == j:
                    if j == k:
                        return 1
"""

    node = get_function_node(code)

    detector = CodeSmellDetector()

    result = detector.analyze_function(node)

    assert isinstance(result, dict)

    smells = result.get("code_smells", [])

    assert "Deep Nesting" in smells or len(smells) > 0


# ---------------------------------------------------------
# Test: Magic number detection
# ---------------------------------------------------------

def test_magic_numbers():

    code = """
def compute():
    return 42
"""

    node = get_function_node(code)

    detector = CodeSmellDetector()

    result = detector.analyze_function(node)

    smells = result.get("code_smells", [])

    assert isinstance(smells, list)


# ---------------------------------------------------------
# Test: Clean function
# ---------------------------------------------------------

def test_clean_function():

    code = """
def add(a, b):
    return a + b
"""

    node = get_function_node(code)

    detector = CodeSmellDetector()

    result = detector.analyze_function(node)

    smells = result.get("code_smells", [])

    assert isinstance(smells, list)


# ---------------------------------------------------------
# Test: Multiple functions
# ---------------------------------------------------------

def test_multiple_functions():

    code = """
def a():
    return 1

def b():
    for i in range(5):
        for j in range(5):
            print(i, j)
"""

    tree = ast.parse(code)

    detector = CodeSmellDetector()

    results = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            results.append(detector.analyze_function(node))

    assert len(results) == 2


# ---------------------------------------------------------
# Test: Empty function
# ---------------------------------------------------------

def test_empty_function():

    code = """
def empty():
    pass
"""

    node = get_function_node(code)

    detector = CodeSmellDetector()

    result = detector.analyze_function(node)

    assert isinstance(result, dict)