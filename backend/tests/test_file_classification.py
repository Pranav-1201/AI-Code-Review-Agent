"""Phase L / S9 — fixture corpora are not production code.

Nothing covered classify_file_type before this file, so these tests also pin
the pre-existing roles against accidental change.
"""
import pytest

from backend.app.services.repo_analyzer import (
    classify_file_type,
    coarse_file_type,
)

FIXTURE_PATHS = [
    "backend/benchmark/corpus/fixtures/f1_sql/main.py",
    "some_repo/tests/fixtures/sample.py",
    "pkg/corpus/planted.py",
    "pkg/testdata/vuln.py",
    # Windows separators must classify identically.
    "backend\\benchmark\\corpus\\fixtures\\f6_dead_functions\\main.py",
]


@pytest.mark.parametrize("path", FIXTURE_PATHS)
def test_fixture_paths_get_the_fixture_role(path):
    assert classify_file_type(path, "x = 1\n") == "fixture"


@pytest.mark.parametrize("path", FIXTURE_PATHS)
def test_fixture_role_is_not_production(path):
    assert coarse_file_type(classify_file_type(path, "x = 1\n")) == "test"


def test_coarse_contract_stays_three_valued():
    """The scoring layer and the frontend understand exactly these three."""
    roles = ["test", "non_code", "fixture", "utility", "cli_parser",
             "data_model", "orchestrator"]
    assert {coarse_file_type(r) for r in roles} <= {
        "production", "test", "non_code"}


def test_ordinary_production_file_is_unaffected():
    assert classify_file_type("backend/app/services/thing.py", "x = 1\n") == "utility"
    assert coarse_file_type("utility") == "production"


def test_a_test_file_is_still_a_test_file():
    assert classify_file_type("backend/tests/test_thing.py", "x = 1\n") == "test"
