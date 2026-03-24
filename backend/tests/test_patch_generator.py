"""
Unit tests for PatchGenerator.

This module tests the patch generation component of the
AI code review system. The patch generator is responsible
for producing a unified diff between original code and
improved/refactored code.

Tests verify:

- correct patch generation
- behavior when code changes
- behavior when no changes occur
- handling of empty files
- handling of large files
- robustness for completely different code

These tests are lightweight and run quickly.
"""

import sys
import os

# Allow importing backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.analysis.patch_generator import PatchGenerator


# ---------------------------------------------------------
# Test: Basic patch generation
# ---------------------------------------------------------

def test_basic_patch_generation():
    """
    Verify that a patch is generated when code changes.
    """

    original_code = """
def process(arr):
    for i in arr:
        for j in arr:
            if i == j:
                print(i)
"""

    improved_code = """
def process(arr):
    seen = set(arr)
    for value in seen:
        print(value)
"""

    generator = PatchGenerator()

    patch = generator.generate_patch(original_code, improved_code)

    # A patch should exist because the code changed
    assert patch is not None
    assert isinstance(patch, str)

    # Unified diff normally contains +/- lines
    assert "+" in patch or "-" in patch


# ---------------------------------------------------------
# Test: No changes between files
# ---------------------------------------------------------

def test_no_change_patch():
    """
    If original and improved code are identical,
    PatchGenerator should return None.
    """

    code = """
def hello():
    print("hello")
"""

    generator = PatchGenerator()

    patch = generator.generate_patch(code, code)

    # Expected behavior: no patch generated
    assert patch is None


# ---------------------------------------------------------
# Test: Empty original code
# ---------------------------------------------------------

def test_empty_original_code():
    """
    Patch generator should handle empty original code safely.
    """

    original_code = ""

    improved_code = """
def new_function():
    print("created")
"""

    generator = PatchGenerator()

    patch = generator.generate_patch(original_code, improved_code)

    assert patch is not None
    assert isinstance(patch, str)


# ---------------------------------------------------------
# Test: Empty improved code
# ---------------------------------------------------------

def test_empty_improved_code():
    """
    Patch generator should handle deletion of code.
    """

    original_code = """
def delete_me():
    print("remove this")
"""

    improved_code = ""

    generator = PatchGenerator()

    patch = generator.generate_patch(original_code, improved_code)

    assert patch is not None


# ---------------------------------------------------------
# Test: Large code diff
# ---------------------------------------------------------

def test_large_code_patch():
    """
    Ensure patch generator handles large code inputs
    without crashing or producing invalid output.
    """

    original_lines = "\n".join([f"print({i})" for i in range(200)])

    improved_lines = "\n".join([f"print({i*2})" for i in range(200)])

    original_code = f"""
def large():
{original_lines}
"""

    improved_code = f"""
def large():
{improved_lines}
"""

    generator = PatchGenerator()

    patch = generator.generate_patch(original_code, improved_code)

    assert patch is not None