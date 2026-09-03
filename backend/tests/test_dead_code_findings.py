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
