"""
npm CVE lookup via OSV.dev (Phase C / roadmap A4).

`dependency_analyzer` already queried OSV, but the enrichment loop skipped every
non-Python dependency (`if dep["type"] not in ("python",): continue`), so node
and node-dev packages were parsed, displayed, and then reported at risk_level
"Low" no matter what was known about them. npm is where the bulk of published
CVEs live, so the ecosystem with the most vulnerability data had none of it.

The hard part is not the query, it is *which version to ask about*. package.json
records a RANGE, and `^` is npm's default, so almost nothing is exactly pinned.
Asking OSV about the floor of `^4.17.20` reports CVE-2021-23337 against a repo
whose lockfile actually installs the patched 4.17.21 — a false positive on
nearly every project, which is the precise failure mode Phase C/A2 spent its
budget removing. So the resolution order is:

  1. package-lock.json — the exact version npm actually installs.
  2. an exact pin in package.json ("1.2.3", "=1.2.3", "v1.2.3").
  3. otherwise DO NOT QUERY. An unresolvable range is unmeasured, and this
     project's standing rule is that unmeasured never gets scored as clean.

These tests pin each step, and pin that a range without a lockfile stays silent
rather than guessing.
"""

import json

import pytest

from backend.app.analysis import dependency_analyzer as da


# ----------------------------------------------------------
# Step 2: exact-pin detection in a package.json spec
# ----------------------------------------------------------

@pytest.mark.parametrize("spec,expected", [
    ("1.2.3", "1.2.3"),
    ("=1.2.3", "1.2.3"),
    ("v1.2.3", "1.2.3"),
    ("  1.2.3  ", "1.2.3"),
    ("1.2.3-beta.1", "1.2.3-beta.1"),
])
def test_exact_pins_are_resolved(spec, expected):
    assert da._exact_npm_version(spec) == expected


@pytest.mark.parametrize("spec", [
    "^1.2.3",       # npm's default — a range, not a pin
    "~1.2.3",
    ">=1.2.3",
    "1.2.x",
    "1.x",
    "*",
    "latest",
    "",
    ">=1.2.3 <2.0.0",
    "1.2.3 || 2.0.0",
    "npm:other-pkg@1.2.3",   # alias: the name is wrong, not just the version
    "git+https://github.com/o/r.git#v1.2.3",
    "file:../local",
    "link:../local",
    "workspace:*",
])
def test_ranges_and_non_registry_specs_are_not_resolved(spec):
    assert da._exact_npm_version(spec) is None


# ----------------------------------------------------------
# Step 1: package-lock.json gives the version actually installed
# ----------------------------------------------------------

def test_lockfile_v3_yields_installed_versions(tmp_path):
    (tmp_path / "package-lock.json").write_text(json.dumps({
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "app"},
            "node_modules/lodash": {"version": "4.17.21"},
            "node_modules/express": {"version": "4.18.2"},
        },
    }), encoding="utf-8")

    assert da._npm_locked_versions(str(tmp_path)) == {
        "lodash": "4.17.21",
        "express": "4.18.2",
    }


def test_lockfile_v1_yields_installed_versions(tmp_path):
    (tmp_path / "package-lock.json").write_text(json.dumps({
        "lockfileVersion": 1,
        "dependencies": {
            "lodash": {"version": "4.17.21"},
        },
    }), encoding="utf-8")

    assert da._npm_locked_versions(str(tmp_path)) == {"lodash": "4.17.21"}


def test_nested_transitive_copies_do_not_shadow_the_top_level_one(tmp_path):
    """A nested node_modules entry is a *different* copy for a different parent.

    Letting it win would report a CVE against a version the app does not
    directly depend on.
    """
    (tmp_path / "package-lock.json").write_text(json.dumps({
        "lockfileVersion": 3,
        "packages": {
            "node_modules/lodash": {"version": "4.17.21"},
            "node_modules/some-dep/node_modules/lodash": {"version": "4.17.11"},
        },
    }), encoding="utf-8")

    assert da._npm_locked_versions(str(tmp_path))["lodash"] == "4.17.21"


def test_missing_lockfile_is_empty_not_an_error(tmp_path):
    assert da._npm_locked_versions(str(tmp_path)) == {}


def test_corrupt_lockfile_is_empty_not_an_error(tmp_path):
    (tmp_path / "package-lock.json").write_text("{not json", encoding="utf-8")
    assert da._npm_locked_versions(str(tmp_path)) == {}


# ----------------------------------------------------------
# End-to-end wiring through analyze_dependencies
# ----------------------------------------------------------

class _RecordedOSV(list):
    """The list of (ecosystem, name, version) queries, plus canned answers."""
    answers: dict


@pytest.fixture
def osv_calls(monkeypatch):
    """Record every OSV query and serve canned answers. No network."""
    calls = _RecordedOSV()
    calls.answers = {}

    def fake_query(name, version, ecosystem="PyPI"):
        calls.append((ecosystem, name, version))
        return calls.answers.get((ecosystem, name, version), [])

    monkeypatch.setattr(da, "_query_osv", fake_query)
    monkeypatch.setattr(da, "_fetch_latest_pypi_version", lambda name: None)
    return calls


def _write_package_json(tmp_path, deps=None, dev_deps=None):
    (tmp_path / "package.json").write_text(json.dumps({
        "dependencies": deps or {},
        "devDependencies": dev_deps or {},
    }), encoding="utf-8")


def test_node_dependency_is_queried_against_the_npm_ecosystem(tmp_path, osv_calls):
    _write_package_json(tmp_path, deps={"lodash": "4.17.20"})

    da.analyze_dependencies(str(tmp_path))

    assert ("npm", "lodash", "4.17.20") in osv_calls


def test_dev_dependency_is_queried_too(tmp_path, osv_calls):
    _write_package_json(tmp_path, dev_deps={"vite": "5.0.0"})

    da.analyze_dependencies(str(tmp_path))

    assert ("npm", "vite", "5.0.0") in osv_calls


def test_lockfile_version_wins_over_the_package_json_range(tmp_path, osv_calls):
    _write_package_json(tmp_path, deps={"lodash": "^4.17.20"})
    (tmp_path / "package-lock.json").write_text(json.dumps({
        "lockfileVersion": 3,
        "packages": {"node_modules/lodash": {"version": "4.17.21"}},
    }), encoding="utf-8")

    da.analyze_dependencies(str(tmp_path))

    assert ("npm", "lodash", "4.17.21") in osv_calls
    assert ("npm", "lodash", "4.17.20") not in osv_calls


def test_unresolvable_range_without_a_lockfile_is_never_queried(tmp_path, osv_calls):
    """The FP-avoidance rule: don't guess that the range floor is installed."""
    _write_package_json(tmp_path, deps={"lodash": "^4.17.20", "react": "*"})

    da.analyze_dependencies(str(tmp_path))

    assert [c for c in osv_calls if c[0] == "npm"] == []


def test_a_known_npm_cve_raises_the_risk_level(tmp_path, osv_calls):
    osv_calls.answers[("npm", "lodash", "4.17.20")] = [
        {"id": "GHSA-35jh-r3h4-6jhm", "summary": "Command injection", "severity": "High"},
    ]
    _write_package_json(tmp_path, deps={"lodash": "4.17.20"})

    deps = da.analyze_dependencies(str(tmp_path))
    lodash = next(d for d in deps if d["name"] == "lodash")

    assert lodash["risk_level"] == "High"
    assert [v["id"] for v in lodash["vulnerabilities"]] == ["GHSA-35jh-r3h4-6jhm"]


def test_a_clean_npm_package_keeps_its_low_risk_and_empty_vuln_list(tmp_path, osv_calls):
    _write_package_json(tmp_path, deps={"lodash": "4.17.21"})

    deps = da.analyze_dependencies(str(tmp_path))
    lodash = next(d for d in deps if d["name"] == "lodash")

    assert lodash["risk_level"] == "Low"
    assert lodash["vulnerabilities"] == []


def test_reported_version_is_the_one_the_cve_was_checked_against(tmp_path, osv_calls):
    """A finding keyed to a version the UI never shows cannot be verified.

    package.json says `^4.17.20`; the lockfile installs 4.17.21. Displaying the
    range floor next to a CVE looked up for 4.17.21 invites the reader to check
    the wrong version.
    """
    osv_calls.answers[("npm", "lodash", "4.17.21")] = [
        {"id": "GHSA-x", "summary": "s", "severity": "High"},
    ]
    _write_package_json(tmp_path, deps={"lodash": "^4.17.20"})
    (tmp_path / "package-lock.json").write_text(json.dumps({
        "lockfileVersion": 3,
        "packages": {"node_modules/lodash": {"version": "4.17.21"}},
    }), encoding="utf-8")

    deps = da.analyze_dependencies(str(tmp_path))
    lodash = next(d for d in deps if d["name"] == "lodash")

    assert lodash["version"] == "4.17.21"


def test_unresolvable_range_still_displays_the_package_json_spec(tmp_path, osv_calls):
    """Nothing was looked up, so nothing should be restated as installed."""
    _write_package_json(tmp_path, deps={"lodash": "^4.17.20"})

    deps = da.analyze_dependencies(str(tmp_path))
    lodash = next(d for d in deps if d["name"] == "lodash")

    assert lodash["version"] == "4.17.20"


def test_python_dependencies_still_use_the_pypi_ecosystem(tmp_path, osv_calls):
    """A4 must not disturb the PyPI path it is extending."""
    (tmp_path / "requirements.txt").write_text("flask==2.0.1\n", encoding="utf-8")

    da.analyze_dependencies(str(tmp_path))

    assert ("PyPI", "flask", "2.0.1") in osv_calls
