"""Phase L / S8 — the two false positives that made wiring unsafe."""

from backend.app.analysis.call_graph import (
    build_interprocedural_graph,
    find_dead_functions,
)


def _dead_names(sources):
    return {n.name for n in find_dead_functions(
        build_interprocedural_graph(sources))}


def test_pytest_named_functions_are_not_dead():
    """pytest collects test_* by name, with no decorator to key off."""
    sources = {"backend/tests/test_thing.py": (
        "def test_one():\n"
        "    assert True\n"
        "\n"
        "class TestGroup:\n"
        "    def test_two(self):\n"
        "        assert True\n"
    )}
    assert _dead_names(sources) == set()


def test_override_of_an_external_base_is_not_dead():
    """JsonFormatter.format is called by the stdlib, never by name here."""
    sources = {"backend/app/observability.py": (
        "import logging\n"
        "\n"
        "class JsonFormatter(logging.Formatter):\n"
        "    def format(self, record):\n"
        "        return record.getMessage()\n"
    )}
    assert _dead_names(sources) == set()


def test_a_genuinely_orphaned_function_is_still_dead():
    """The guards must not blanket-exempt. Recall has to survive."""
    sources = {"pkg/main.py": (
        "def _never_called():\n"
        "    return 1\n"
        "\n"
        "def main():\n"
        "    return 2\n"
    )}
    assert _dead_names(sources) == {"_never_called"}


def test_a_method_of_a_locally_defined_base_is_still_dead():
    """The external-base guard keys on 'not defined here', not 'has a base'."""
    sources = {"pkg/a.py": (
        "class Base:\n"
        "    pass\n"
        "\n"
        "class Child(Base):\n"
        "    def orphan(self):\n"
        "        return 1\n"
    )}
    assert _dead_names(sources) == {"orphan"}


# ==========================================================
# S8b: the wiring — findings the detector has always produced
# and the report has always discarded.
# ==========================================================

from backend.app.analysis.heuristic_refactor_engine import HeuristicRefactorEngine
from backend.app.services.repository_review_engine import analyze_single_file

_SRC = (
    "import os\n"
    "import json\n"
    "\n"
    "\n"
    "def used():\n"
    "    return json.dumps({})\n"
    "\n"
    "\n"
    "def orphan():\n"
    "    return 1\n"
)


def _analyse(file_type="production", file_role="utility"):
    return analyze_single_file({
        "content": _SRC,
        "file_name": "sample.py",
        "file_path": "pkg/sample.py",
        "language": "Python",
        "file_type": file_type,
        "file_role": file_role,
        "imports": ["os", "json"],
        "dead_code": {
            "unused_imports": ["os"],
            "unused_functions": ["orphan"],
        },
    }, HeuristicRefactorEngine())


def _of_type(result, kind):
    return [i for i in result["issues"] if i["type"] == kind]


def test_dead_import_reaches_the_report_with_a_real_location():
    found = _of_type(_analyse(), "dead_import")
    assert len(found) == 1
    assert found[0]["line"] == 1              # `import os`
    assert found[0]["snippet"]                # never a placeholder
    assert "os" in found[0]["message"]
    assert found[0]["severity"] == "low"


def test_dead_function_reaches_the_report_with_a_real_location():
    found = _of_type(_analyse(), "dead_function")
    assert len(found) == 1
    assert found[0]["line"] == 9              # `def orphan():`
    assert found[0]["snippet"]
    assert "orphan" in found[0]["message"]


def test_dead_functions_are_production_only():
    """374 of the 462 measured dead functions live in backend/tests."""
    assert _of_type(_analyse(file_type="test", file_role="test"),
                    "dead_function") == []


def test_dead_imports_are_reported_in_test_files_too():
    assert len(_of_type(_analyse(file_type="test", file_role="test"),
                        "dead_import")) == 1


def test_a_fixture_file_emits_nothing_at_all():
    result = _analyse(file_type="test", file_role="fixture")
    assert result["issues"] == []
    assert result["security_risks"] == []


def test_every_finding_carries_its_file_type():
    result = _analyse()
    assert result["issues"]
    assert all(i["file_type"] == "production" for i in result["issues"])


def test_identical_content_in_different_roles_does_not_share_a_cache_entry():
    """The cache key is (version, content, imports) — the role was missing.

    A fixture whose content matches a production file must not be served the
    production file's findings.
    """
    prod = _analyse()
    fixture = _analyse(file_type="test", file_role="fixture")
    assert prod["issues"], "control: the production file must report something"
    assert fixture["issues"] == []
