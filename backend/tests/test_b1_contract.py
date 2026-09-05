"""B1 — the contract the decomposition must not change.

These are *characterization* tests, not TDD tests: they describe behaviour
that already exists, so they pass on first run against unmodified code. A
test that has never been red proves nothing, so each one was watched failing
against a deliberately perturbed copy of the function before being committed
(see `docs/superpowers/plans/2026-09-05-b1-decompose.md`, Tasks 1 and 4).

They are deliberately about *shape and invariants*, not values: the byte-level
guarantee comes from a separate gate that runs both functions over this whole
repository and compares 5.4 MB of canonical JSON. This file is the fast half
that CI can afford to run.
"""
import json

import pytest

from backend.app.analysis import dependency_analyzer as da
from backend.app.analysis.heuristic_refactor_engine import HeuristicRefactorEngine
from backend.app.services.repository_review_engine import RepositoryReviewEngine


# ==========================================================
# analyze_dependencies — six manifest parsers and one contract
# ==========================================================

def _write_manifest_repo(tmp_path):
    """One repository carrying all six manifests this parser understands."""
    (tmp_path / "requirements.txt").write_text(
        "# comment\n-e .\n\nflask>=2.0\nrequests==2.31.0\npytest\n",
        encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({
        "dependencies": {"lodash": "^4.17.20"},
        "devDependencies": {"vite": "5.0.0"},
    }), encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = [\n  "click>=8.0",\n  "rich==13.7.0",\n]\n'
        '[build-system]\nrequires = ["flit_core==3.11,<4"]\n',
        encoding="utf-8")
    (tmp_path / "Pipfile").write_text(
        '[packages]\nboto3 = ">=1.0"\n[dev-packages]\nblack = "==24.1.0"\n',
        encoding="utf-8")
    (tmp_path / "setup.py").write_text(
        'setup(install_requires=["urllib3", "certifi"])\n', encoding="utf-8")
    (tmp_path / "setup.cfg").write_text(
        "[options]\ninstall_requires =\n    jinja2>=3.0\n    markupsafe\n",
        encoding="utf-8")
    return str(tmp_path)


@pytest.fixture
def no_network(monkeypatch):
    """Enrichment reaches the network; these tests are about parsing."""
    monkeypatch.setattr(da, "_fetch_latest_pypi_version", lambda name: None)
    monkeypatch.setattr(da, "_query_osv",
                        lambda name, version, ecosystem="PyPI": ([], "checked"))


@pytest.fixture
def deps(tmp_path, no_network):
    return {d["name"].lower(): d
            for d in da.analyze_dependencies(_write_manifest_repo(tmp_path))}


def test_every_manifest_is_read(deps):
    """One name from each of the six files. A parser that stops being
    reached during the decomposition shows up here and nowhere else."""
    for name in ("flask", "lodash", "click", "boto3", "urllib3", "jinja2"):
        assert name in deps, f"{name} missing — a parser was not reached"


def test_an_exact_pin_is_recorded_as_pinned(deps):
    assert deps["requests"]["version"] == "2.31.0"
    assert deps["requests"]["version_source"] == "pinned"


def test_a_range_keeps_its_constraint_and_stays_unknown(deps):
    """PHASE H / S7: `flask>=2.0` must not be recorded as version 2.0."""
    assert deps["flask"]["version"] == "unknown"
    assert deps["flask"]["constraint"] == ">=2.0"
    assert deps["flask"]["version_source"] == "unpinned"


def test_a_bare_name_is_unspecified(deps):
    assert deps["pytest"]["version"] == "unknown"
    assert deps["pytest"]["constraint"] == ""
    assert deps["pytest"]["version_source"] == "unspecified"


def test_a_multi_clause_specifier_never_lands_in_the_version_field(deps):
    """`"flit_core==3.11,<4"` used to be stored verbatim as a version."""
    assert "," not in deps["flit_core"]["version"]


def test_setup_cfg_versioned_requirements_are_recorded(deps):
    """The continuation test used to read `stripped`, whose indentation had
    already been removed — so the section closed on its own first line and no
    versioned setup.cfg dependency was ever recorded."""
    assert "jinja2" in deps and "markupsafe" in deps


def test_node_dev_dependencies_carry_their_own_type(deps):
    assert deps["lodash"]["type"] == "node"
    assert deps["vite"]["type"] == "node-dev"


def test_every_dependency_carries_the_full_contract(deps):
    required = {"name", "version", "constraint", "version_source",
                "vuln_lookup", "latest_version", "is_outdated",
                "risk_level", "vulnerabilities", "type"}
    for dep in deps.values():
        assert required <= set(dep), f"{dep['name']} is missing keys"


def test_a_repository_with_no_manifests_returns_an_empty_list(tmp_path,
                                                              no_network):
    assert da.analyze_dependencies(str(tmp_path)) == []


# ==========================================================
# review_repository — the report shape
# ==========================================================

def _repo_data():
    prod = (
        "import os\n\n\ndef handler(items):\n"
        "    out = []\n"
        "    for i in items:\n"
        "        if i:\n"
        "            out.append(i)\n"
        "    return out\n"
    )
    return [
        {"file_path": "pkg/service.py", "file_name": "service.py",
         "content": prod, "language": "Python", "is_code": True,
         "lines": prod.count("\n"), "imports": ["os"],
         "file_type": "production", "file_role": "utility",
         "dead_code": {"unused_imports": ["os"], "unused_functions": []}},
        {"file_path": "tests/test_service.py", "file_name": "test_service.py",
         "content": "def test_handler():\n    assert True\n",
         "language": "Python", "is_code": True, "lines": 2, "imports": [],
         "file_type": "test", "file_role": "test",
         "dead_code": {"unused_imports": [], "unused_functions": []}},
        {"file_path": "README.md", "file_name": "README.md",
         "content": "# hi\n", "language": "Markdown", "is_code": False,
         "lines": 1, "imports": []},
    ]


def _engine():
    engine = RepositoryReviewEngine()
    engine.refactor_engine = HeuristicRefactorEngine()
    return engine


@pytest.fixture
def report(tmp_path):
    return _engine().review_repository(str(tmp_path), _repo_data())


def test_the_report_carries_every_top_level_key(report):
    assert set(report) == {
        "repository_summary", "file_reports", "issues", "dependencies",
        "dependency_graph", "duplicates", "visualizations", "insights",
        "frameworks", "architecture",
    }


def test_non_code_files_get_a_report_but_no_analysis(report):
    readme = next(f for f in report["file_reports"]
                  if f["file_name"] == "README.md")
    assert readme["score"] == 100
    assert readme["file_type"] == "non_code"
    assert readme["issues"] == [] and readme["security_risks"] == []
    assert readme["complexity"] == "N/A"


#: Keys the code-file report carries and the non-code report does not.
#: Measured, not assumed. Two separate dict literals build these reports and
#: they have drifted: a non-code row reaches the frontend without
#: `time_complexity`, so anything reading that field off the file table gets
#: `undefined` for every README in the repository.
#:
#: This is a real inconsistency and it is NOT fixed as part of B1 — B1 is a
#: decomposition gated on byte-identical output, and closing this changes the
#: bytes. It is closed in its own commit afterwards, with its own test.
KNOWN_NON_CODE_KEY_GAP = {"patch", "refactor_changes", "time_complexity"}


def test_the_two_file_report_builders_differ_only_in_the_known_gap(report):
    """Two builders produce these — a non-code one and a code one. This test
    exists to catch NEW drift between them, so it pins the existing gap
    exactly rather than tolerating any difference."""
    code = set(next(f for f in report["file_reports"]
                    if f["file_name"] == "service.py"))
    non_code = set(next(f for f in report["file_reports"]
                        if f["file_name"] == "README.md"))

    assert code - non_code == KNOWN_NON_CODE_KEY_GAP
    assert non_code - code == set(), \
        "the non-code report grew a key the code report lacks"


def test_the_summary_counts_separate_code_from_production(report):
    s = report["repository_summary"]
    assert s["files_analyzed"] == 3
    assert s["code_files"] == 2
    assert s["production_files"] == 1
    assert s["non_production_files"] == 1


def test_the_health_score_is_the_documented_weighted_composite(report):
    """F14 surfaces these weights in the UI; they must stay in sync."""
    s = report["repository_summary"]
    expected = round(
        0.35 * s["average_quality_score"] +
        0.25 * (100 if s["total_security_issues"] == 0
                else max(0, round(100 - (s["total_security_issues"] ** 0.7) * 10))) +
        0.20 * s["avg_documentation_coverage"] +
        0.20 * max(0, round(100 - min(s["avg_cyclomatic_complexity"] * 3, 80)))
    )
    assert s["health_score"] == expected


def test_paths_are_normalised_to_forward_slashes(report):
    assert all("\\" not in f["file_path"] for f in report["file_reports"])


def test_insights_name_their_four_fields(report):
    assert set(report["insights"]) == {
        "top_critical_issues", "most_complex_files",
        "most_central_file", "most_reused_module"}


def test_an_empty_repository_still_returns_a_whole_report(tmp_path):
    """And scores 45 out of 100 on nothing at all.

    This is the B6 finding, pinned at the layer that produces it. With zero
    production files the composite reads quality 0 and documentation 0, but
    security and simplicity have nothing to subtract from and default to 100:

        0.35*0 + 0.25*100 + 0.20*0 + 0.20*100  ==  45

    The engine is not where that gets fixed — B6 rejects an unanalysable
    repository upstream, before a user is ever shown a number. This test
    pins 45 so that if the rejection is ever bypassed, the failure is loud
    here rather than silent in front of a user.
    """
    empty = _engine().review_repository(str(tmp_path), [])
    assert empty["repository_summary"]["health_score"] == 45
    assert empty["repository_summary"]["production_files"] == 0
    assert empty["file_reports"] == []
    assert empty["insights"]["most_reused_module"] == "None"
