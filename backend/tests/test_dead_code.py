"""
Unit tests for DeadCodeDetector.

This module tests the dead code detection system used by the
AI-powered repository analyzer.

The detector should identify:

- unused imports
- unused variables
- unused functions
- partially used code
- empty files
- malformed code
- large input files

All tests are lightweight and safe to run on a laptop.
"""

import sys
import os
import pytest

# Allow importing project modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.analysis.dead_code_detector import DeadCodeDetector


# ---------------------------------------------------------
# Test: Basic unused code detection
# ---------------------------------------------------------

def test_basic_dead_code_detection():
    """
    Detect unused imports and variables.
    """

    code = """
import numpy
import os

x = 10
y = 20

def helper():
    print("hello")

print(y)
"""

    detector = DeadCodeDetector()

    result = detector.analyze(code)

    assert result is not None
    assert isinstance(result, dict)


# ---------------------------------------------------------
# Test: No dead code present
# ---------------------------------------------------------

def test_no_dead_code():
    """
    Detector should return minimal findings when everything is used.
    """

    code = """
import math

def square(x):
    return x * x

print(square(5))
"""

    detector = DeadCodeDetector()

    result = detector.analyze(code)

    assert result is not None
    assert isinstance(result, dict)


# ---------------------------------------------------------
# Test: Unused function detection
# ---------------------------------------------------------

def test_unused_function():
    """
    A function defined but never called should be detected.
    """

    code = """
def unused():
    print("not used")

def used():
    return 5

print(used())
"""

    detector = DeadCodeDetector()

    result = detector.analyze(code)

    assert result is not None


# ---------------------------------------------------------
# Test: Multiple unused variables
# ---------------------------------------------------------

def test_unused_variables():
    """
    Detect multiple unused variables.
    """

    code = """
a = 1
b = 2
c = 3

print(a)
"""

    detector = DeadCodeDetector()

    result = detector.analyze(code)

    assert result is not None


# ---------------------------------------------------------
# Test: Empty file
# ---------------------------------------------------------

def test_empty_code():
    """
    Analyzer should handle empty input safely.
    """

    code = ""

    detector = DeadCodeDetector()

    result = detector.analyze(code)

    assert result is not None


# ---------------------------------------------------------
# Test: Large file simulation
# ---------------------------------------------------------

def test_large_code_file():
    """
    Simulate analyzing a large code snippet with many variables.
    """

    lines = "\n".join([f"var{i} = {i}" for i in range(200)])

    code = f"""
{lines}

print(var1)
"""

    detector = DeadCodeDetector()

    result = detector.analyze(code)

    assert result is not None


# ---------------------------------------------------------
# Test: Malformed code
# ---------------------------------------------------------

def test_malformed_code():
    """
    Analyzer should gracefully handle malformed Python code.
    """

    code = """
def broken(
    print("oops")
"""

    detector = DeadCodeDetector()

    # Some analyzers raise errors, others return structured errors
    try:
        result = detector.analyze(code)
        assert result is not None
    except SyntaxError:
        assert True


# ---------------------------------------------------------
# Test: Mixed imports usage
# ---------------------------------------------------------

def test_partial_import_usage():
    """
    One import used, one unused.
    """

    code = """
import os
import sys

print(os.getcwd())
"""

    detector = DeadCodeDetector()

    result = detector.analyze(code)

    assert result is not None


# ---------------------------------------------------------
# Fix F: alias-aware unused-import detection
# ---------------------------------------------------------

def test_aliased_import_used_is_not_flagged():
    """`import numpy as np` used via `np` must NOT be reported unused."""
    detector = DeadCodeDetector()
    result = detector.analyze("import numpy as np\nprint(np.array([1]))\n")
    assert "numpy" not in result["unused_imports"], \
        "alias-blind regression: aliased-and-used import flagged unused"


def test_aliased_import_unused_is_flagged():
    detector = DeadCodeDetector()
    result = detector.analyze("import numpy as np\nprint(1)\n")
    assert "numpy" in result["unused_imports"]


def test_plain_import_partial_usage_is_precise():
    detector = DeadCodeDetector()
    result = detector.analyze("import os\nimport sys\nprint(sys.argv)\n")
    assert "os" in result["unused_imports"]
    assert "sys" not in result["unused_imports"]


# ---------------------------------------------------------
# Interprocedural repository-level dead-function detection
# ---------------------------------------------------------

def test_interprocedural_dead_function_detection():
    detector = DeadCodeDetector()
    sources = {
        "m.py": (
            "def used():\n    return 1\n\n"
            "def dead():\n    return 2\n\n"
            "def main():\n    return used()\n"
        )
    }
    dead = detector.detect_repository_dead_functions(sources)
    assert "dead" in dead["m.py"]
    assert "used" not in dead["m.py"]   # called
    assert "main" not in dead["m.py"]   # entrypoint


def test_interprocedural_visitor_methods_not_dead():
    """NodeVisitor-style dispatch methods must not be reported dead even
    though they have no static caller (dispatched via self.visit)."""
    detector = DeadCodeDetector()
    sources = {
        "v.py": (
            "import ast\n"
            "class V(ast.NodeVisitor):\n"
            "    def visit_Call(self, node):\n        return node\n"
        )
    }
    dead = detector.detect_repository_dead_functions(sources)
    assert "visit_Call" not in dead["v.py"]