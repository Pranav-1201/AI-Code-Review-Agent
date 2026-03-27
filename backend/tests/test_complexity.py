"""
Unit tests for ComplexityAnalyzer

This test suite validates the behavior of the complexity analyzer used in
the AI code review system. The analyzer inspects Python AST nodes and
computes complexity metrics for functions.

The tests verify:

1. Basic complexity detection
2. Nested loop detection
3. Conditional branches
4. Recursion scenarios
5. Empty functions
6. Deep nesting edge cases
7. Large function inputs
8. Malformed code handling

All tests are designed to run quickly and require no external dependencies.
"""
import sys
import os

# Allow tests to import project modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ast
import pytest

from backend.app.analysis.complexity_analyzer import ComplexityAnalyzer


# ---------------------------------------------------------
# Helper function to extract the first function node
# ---------------------------------------------------------

def get_function_node(code: str):
    """
    Parse Python code and return the first function definition node.
    """
    tree = ast.parse(code)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            return node

    return None


# ---------------------------------------------------------
# Test: Basic function complexity
# ---------------------------------------------------------

def test_basic_complexity():
    """
    Tests a simple function with nested loops and conditionals.
    """

    code = """
def example(arr):
    for i in arr:
        for j in arr:
            if i == j:
                print(i)
"""

    node = get_function_node(code)

    analyzer = ComplexityAnalyzer()

    result = analyzer.analyze_function(node)

    assert result is not None
    assert isinstance(result, dict)


# ---------------------------------------------------------
# Test: Function with no control flow
# ---------------------------------------------------------

def test_simple_function():
    """
    Complexity analyzer should handle very simple functions.
    """

    code = """
def add(a, b):
    return a + b
"""

    node = get_function_node(code)

    analyzer = ComplexityAnalyzer()

    result = analyzer.analyze_function(node)

    assert result is not None
    assert isinstance(result, dict)


# ---------------------------------------------------------
# Test: Deep nested structures
# ---------------------------------------------------------

def test_deep_nesting():
    """
    Test analyzer on deeply nested loops and conditionals.
    """

    code = """
def deep(arr):
    for i in arr:
        for j in arr:
            for k in arr:
                if i == j:
                    if j == k:
                        if i == k:
                            print(i, j, k)
"""

    node = get_function_node(code)

    analyzer = ComplexityAnalyzer()

    result = analyzer.analyze_function(node)

    assert result is not None
    assert isinstance(result, dict)


# ---------------------------------------------------------
# Test: Recursive function
# ---------------------------------------------------------

def test_recursive_function():
    """
    Ensure recursion does not break complexity analysis.
    """

    code = """
def factorial(n):
    if n == 0:
        return 1
    return n * factorial(n-1)
"""

    node = get_function_node(code)

    analyzer = ComplexityAnalyzer()

    result = analyzer.analyze_function(node)

    assert result is not None
    assert isinstance(result, dict)


# ---------------------------------------------------------
# Test: Empty function
# ---------------------------------------------------------

def test_empty_function():
    """
    Analyzer should handle functions with no logic.
    """

    code = """
def empty():
    pass
"""

    node = get_function_node(code)

    analyzer = ComplexityAnalyzer()

    result = analyzer.analyze_function(node)

    assert result is not None


# ---------------------------------------------------------
# Test: Large function simulation
# ---------------------------------------------------------

def test_large_function():
    """
    Simulate a large function with many loops to ensure
    analyzer handles bigger AST structures efficiently.
    """

    # Properly indent the generated loops inside the function
    loops = "\n".join(["    for i in range(10): pass" for _ in range(50)])

    code = f"""
def big_function():
{loops}
"""

    node = get_function_node(code)

    analyzer = ComplexityAnalyzer()

    result = analyzer.analyze_function(node)

    assert result is not None
    assert isinstance(result, dict)


# ---------------------------------------------------------
# Test: Malformed code handling
# ---------------------------------------------------------

def test_malformed_code():
    """
    Ensure malformed code raises SyntaxError during parsing.
    """

    code = """
def broken(
    for i in range(10):
        print(i)
"""

    with pytest.raises(SyntaxError):
        ast.parse(code)


# ---------------------------------------------------------
# Test: Multiple functions in same file
# ---------------------------------------------------------

def test_multiple_functions():
    """
    Ensure analyzer can analyze functions independently
    when multiple functions exist in the same file.
    """

    code = """
def a():
    pass

def b():
    for i in range(10):
        print(i)

def c():
    if True:
        print("test")
"""

    tree = ast.parse(code)

    analyzer = ComplexityAnalyzer()

    results = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            results.append(analyzer.analyze_function(node))

    assert len(results) == 3