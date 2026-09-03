"""Phase K / B6 — a repository we cannot analyse must say so.

Measured before this test existed: a MATLAB-only repository did not error.
It completed as a successful scan reporting health_score 45 on zero files
analysed, because the composite defaults security and simplicity to 100 when
there is nothing to measure. A confident wrong number is worse than a generic
error, which is what B6 asked to replace.
"""
import os

import pytest

from backend.app.services.repo_analyzer import (
    SUPPORTED_LANGUAGES,
    UnsupportedRepositoryError,
    survey_extensions,
)


@pytest.fixture
def matlab_repo(tmp_path):
    (tmp_path / "solver.m").write_text("function y = solver(x)\n  y = x.^2;\nend\n")
    (tmp_path / "plot_it.m").write_text("plot(1:10);\n")
    (tmp_path / "README.md").write_text("# A MATLAB project\n")
    return str(tmp_path)


@pytest.fixture
def python_repo(tmp_path):
    (tmp_path / "app.py").write_text("def main():\n    return 1\n")
    return str(tmp_path)


def test_survey_counts_the_extensions_actually_present(matlab_repo):
    counts = survey_extensions(matlab_repo)
    assert counts[".m"] == 2
    assert counts[".md"] == 1


def test_survey_skips_ignored_directories(tmp_path):
    pkg = tmp_path / "node_modules" / "left-pad"
    pkg.mkdir(parents=True)
    (pkg / "index.js").write_text("module.exports = 1;\n")
    (tmp_path / "real.m").write_text("x = 1;\n")

    counts = survey_extensions(str(tmp_path))
    assert counts[".m"] == 1
    assert ".js" not in counts, "node_modules must not be surveyed"


def test_a_matlab_repository_is_rejected_with_a_readable_message(matlab_repo):
    from main import run_pipeline

    with pytest.raises(UnsupportedRepositoryError) as excinfo:
        run_pipeline(matlab_repo)

    message = str(excinfo.value)
    # It must name what it found...
    assert "MATLAB" in message
    # ...and what it can actually do.
    for language in ("Python", "JavaScript", "TypeScript", "Java", "C++"):
        assert language in message, f"{language} missing from: {message}"
    # And it must not read like a stack trace.
    assert "Traceback" not in message
    assert "None" not in message


def test_an_empty_repository_says_it_is_empty_not_unsupported(tmp_path):
    from main import run_pipeline

    with pytest.raises(UnsupportedRepositoryError) as excinfo:
        run_pipeline(str(tmp_path))

    assert "no files" in str(excinfo.value).lower()


def test_a_python_repository_still_scans(python_repo):
    from main import run_pipeline

    result = run_pipeline(python_repo)
    assert result["repository_summary"]["files_analyzed"] == 1


def test_one_supported_file_among_many_unsupported_is_enough(tmp_path):
    """A mixed repo is analysed for what we understand, not rejected."""
    from main import run_pipeline

    (tmp_path / "app.py").write_text("def main():\n    return 1\n")
    for i in range(5):
        (tmp_path / f"legacy{i}.m").write_text("x = 1;\n")

    result = run_pipeline(str(tmp_path))
    assert result["repository_summary"]["files_analyzed"] == 1


def test_supported_languages_is_not_empty_and_is_human_readable():
    assert "Python" in SUPPORTED_LANGUAGES
    assert all(not lang.startswith(".") for lang in SUPPORTED_LANGUAGES)
