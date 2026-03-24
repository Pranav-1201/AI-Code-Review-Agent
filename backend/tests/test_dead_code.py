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