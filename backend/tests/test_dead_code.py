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


# ----------------------------------------------------------
# Module-level reachability (Phase C / roadmap A3)
# ----------------------------------------------------------
#
# The call graph resolved calls only inside function bodies, so everything
# executed at import time — the `if __name__ == "__main__":` block, module-level
# registration, class-body assignments — was invisible to it. A function called
# only from there had no incoming edge and was reported dead. That was the
# single false positive holding dead_function precision at 0.67 in fixture F6.


def test_function_called_only_from_main_guard_is_not_dead():
    """The __main__ block is real reachability, not decoration.

    Would fail if: call resolution goes back to walking only function bodies,
    which makes every CLI entrypoint in the codebase look dead.
    """
    detector = DeadCodeDetector()
    sources = {
        "main.py": (
            "def entry():\n    return 1\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    entry()\n"
        )
    }
    dead = detector.detect_repository_dead_functions(sources)
    assert "entry" not in dead["main.py"], dead


def test_function_referenced_only_at_module_level_is_not_dead():
    """A module-level reference as a VALUE (registry, callback) keeps a
    function alive, same as one inside a function body."""
    detector = DeadCodeDetector()
    sources = {
        "reg.py": (
            "def handler():\n    return 1\n"
            "\n"
            "HANDLERS = [handler]\n"
        )
    }
    dead = detector.detect_repository_dead_functions(sources)
    assert "handler" not in dead["reg.py"], dead


def test_module_level_reachability_does_not_resurrect_everything():
    """Widening reachability must not simply stop reporting dead code.

    Would fail if: the module-level pass marks all functions alive (e.g. by
    unioning every name in the module), which would trade the false positive
    for total blindness.
    """
    detector = DeadCodeDetector()
    sources = {
        "m.py": (
            "def entry():\n    return 1\n"
            "\n"
            "def orphan():\n    return 2\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    entry()\n"
        )
    }
    dead = detector.detect_repository_dead_functions(sources)
    assert "orphan" in dead["m.py"], dead
    assert "entry" not in dead["m.py"], dead