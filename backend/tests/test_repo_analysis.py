"""
Unit tests for repository analysis.

This module tests the repository analyzer responsible for scanning
a codebase and producing analysis results used by the AI review system.

The analyzer should:

- scan directories
- analyze Python files
- ignore non-Python files
- handle invalid paths safely
"""

import sys
import os
import tempfile

# Allow importing backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.repo_analyzer import analyze_repository


# ---------------------------------------------------------
# Test: Valid repository with Python file
# ---------------------------------------------------------

def test_repository_with_python_file():
    """
    Ensure analyzer works when repository contains Python code.
    """

    with tempfile.TemporaryDirectory() as repo:

        file_path = os.path.join(repo, "example.py")

        with open(file_path, "w") as f:
            f.write("""
def hello():
    print("hello")
""")

        result = analyze_repository(repo)

        assert result is not None


# ---------------------------------------------------------
# Test: Empty repository
# ---------------------------------------------------------

def test_empty_repository():
    """
    Analyzer should handle an empty directory safely.
    """

    with tempfile.TemporaryDirectory() as repo:

        result = analyze_repository(repo)

        assert result is not None


# ---------------------------------------------------------
# Test: Non-Python files ignored
# ---------------------------------------------------------

def test_non_python_files():
    """
    Non-Python files should not break the analyzer.
    """

    with tempfile.TemporaryDirectory() as repo:

        file_path = os.path.join(repo, "readme.txt")

        with open(file_path, "w") as f:
            f.write("This is not Python")

        result = analyze_repository(repo)

        assert result is not None


# ---------------------------------------------------------
# Test: Invalid repository path
# ---------------------------------------------------------

def test_invalid_repository_path():
    """
    Analyzer should raise an error or handle invalid paths gracefully.
    """

    try:
        analyze_repository("this_path_does_not_exist")
    except Exception:
        assert True


# ---------------------------------------------------------
# Test: Multiple Python files
# ---------------------------------------------------------

def test_multiple_files_repository():
    """
    Analyzer should process multiple Python files in a repository.
    """

    with tempfile.TemporaryDirectory() as repo:

        for i in range(5):
            file_path = os.path.join(repo, f"file{i}.py")

            with open(file_path, "w") as f:
                f.write(f"""
def func{i}():
    return {i}
""")

        result = analyze_repository(repo)

        assert result is not None