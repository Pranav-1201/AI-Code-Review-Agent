"""
Phase H / S7 -- a constraint is not a version.

Measured defects, all from one repository's manifests:

    flask>=2.0            -> version "2.0"
    "flit_core==3.11,<4"  -> version "3.11,<4"
    requests              -> version "unknown"

The middle one is the audit's headline: a whole constraint expression sitting
in a field the report prints as a version, because the pyproject fallback regex
captured everything up to the closing quote.

The first is worse and was not in the audit. A lower bound is not a version.
Storing ">=2.0" as "2.0" invents a fact, and that invented fact is then used as
the OSV query key -- so the report lists CVEs against 2.0 for a project that
may well install 3.0.3. The node side already refuses to do this
(_exact_npm_version); the Python side never got the same treatment.

So `version` now holds a concrete version or "unknown", nothing else. The raw
spec moves to `constraint`, and `version_source` records how the version was
arrived at, so a reader can tell a pin from a guess.
"""

import json
import tempfile
from pathlib import Path

import pytest

from backend.app.analysis.dependency_analyzer import (
    _exact_python_version,
    analyze_dependencies,
)


# ----------------------------------------------------------
# The pin extractor
# ----------------------------------------------------------

@pytest.mark.parametrize("spec, expected", [
    ("==3.1.4", "3.1.4"),
    ("== 3.1.4", "3.1.4"),
    ("==3.11,<4", "3.11"),        # compound, but one clause is an exact pin
    ("<4,==3.11", "3.11"),
    ("===1.0", "1.0"),            # PEP 440 arbitrary equality
])
def test_exact_pins_are_extracted(spec, expected):
    assert _exact_python_version(spec) == expected


@pytest.mark.parametrize("spec", [
    ">=2.0",
    ">2.0",
    "<=4",
    "~=1.4.2",                    # compatible release is a range
    "!=1.2.3",
    "==1.4.*",                    # wildcard pin is not a single version
    ">=2.0,<3",
    "",
    None,
])
def test_ranges_and_wildcards_are_not_pins(spec):
    assert _exact_python_version(spec) is None


# ----------------------------------------------------------
# End to end through the manifests
# ----------------------------------------------------------

def _analyze(files):
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        for name, body in files.items():
            (repo / name).write_text(body, encoding="utf-8")
        return {d["name"].lower(): d for d in analyze_dependencies(str(repo))}


def test_lower_bound_is_not_stored_as_a_version():
    deps = _analyze({"requirements.txt": "flask>=2.0\n"})

    assert deps["flask"]["version"] == "unknown"
    assert deps["flask"]["constraint"] == ">=2.0"
    assert deps["flask"]["version_source"] == "unpinned"


def test_exact_pin_is_stored_as_the_version():
    deps = _analyze({"requirements.txt": "jinja2==3.1.4\n"})

    assert deps["jinja2"]["version"] == "3.1.4"
    assert deps["jinja2"]["version_source"] == "pinned"


def test_compound_constraint_never_reaches_the_version_field():
    """The audit's headline symptom: version == '3.11,<4'."""
    deps = _analyze({
        "pyproject.toml": '[build-system]\nrequires = ["flit_core==3.11,<4"]\n'
    })

    assert deps["flit_core"]["version"] == "3.11"
    assert "," not in deps["flit_core"]["version"]
    assert deps["flit_core"]["constraint"] == "==3.11,<4"


def test_bare_requirement_has_no_version_and_no_constraint():
    deps = _analyze({"requirements.txt": "requests\n"})

    assert deps["requests"]["version"] == "unknown"
    assert deps["requests"]["constraint"] == ""
    assert deps["requests"]["version_source"] == "unspecified"


def test_no_version_field_anywhere_contains_a_constraint_operator():
    """The acceptance criterion, stated as an invariant over the whole report."""
    deps = _analyze({
        "requirements.txt": (
            "flask>=2.0\nrequests\nclick>=8.1.3,<9\njinja2==3.1.4\n"
            "urllib3~=2.2\nwerkzeug!=3.0.1\n"
        ),
        "pyproject.toml": '[build-system]\nrequires = ["flit_core==3.11,<4"]\n',
    })

    offenders = {
        name: d["version"]
        for name, d in deps.items()
        if any(ch in str(d["version"]) for ch in ",<>=!~*")
    }

    assert offenders == {}


def test_pipfile_range_is_not_stored_as_a_version():
    """Pipfile stripped the operator and kept the digits, same as the rest."""
    deps = _analyze({
        "Pipfile": '[packages]\nflask = ">=2.0"\nrequests = "*"\njinja2 = "==3.1.4"\n'
    })

    assert deps["flask"]["version"] == "unknown"
    assert deps["flask"]["constraint"] == ">=2.0"
    assert deps["jinja2"]["version"] == "3.1.4"


def test_setup_cfg_range_is_not_stored_as_a_version():
    deps = _analyze({
        "setup.cfg": "[options]\ninstall_requires =\n    flask>=2.0\n    jinja2==3.1.4\n"
    })

    assert deps["flask"]["version"] == "unknown"
    assert deps["jinja2"]["version"] == "3.1.4"


def test_extras_are_stripped_from_the_name_but_the_pin_survives():
    deps = _analyze({"requirements.txt": "celery[redis]==5.3.6\n"})

    assert "celery" in deps
    assert deps["celery"]["version"] == "5.3.6"
