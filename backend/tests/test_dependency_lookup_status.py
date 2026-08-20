"""
Phase H / S5 -- "0 vulnerabilities" must be distinguishable from "never asked".

The report showed an empty vulnerabilities list for every dependency it could
not look up, which reads to a user as "this dependency is clean". Three quite
different situations produced that identical output:

    checked      OSV answered, and the answer was zero
    unreachable  the request failed -- network, DNS, timeout, 5xx
    skipped      no version to ask about (unpinned, no lockfile)

A security report that cannot tell "clean" from "the lookup was down" is
worse than one that says nothing, because it is trusted.

Worse, `_query_osv` swallowed the exception AND cached the empty list under a
24-hour TTL, so one transient failure would report the package as clean for the
rest of the day.

`vuln_lookup` now carries that status per dependency, and a failed lookup is
not cached.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.analysis import dependency_analyzer as da


@pytest.fixture(autouse=True)
def _clear_caches():
    da._OSV_CACHE.clear()
    da._PYPI_VERSION_CACHE.clear()
    yield
    da._OSV_CACHE.clear()
    da._PYPI_VERSION_CACHE.clear()


def _analyze(files):
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        for name, body in files.items():
            (repo / name).write_text(body, encoding="utf-8")
        return {d["name"].lower(): d for d in da.analyze_dependencies(str(repo))}


# ----------------------------------------------------------
# _query_osv reports HOW the lookup went
# ----------------------------------------------------------

def test_a_successful_empty_answer_is_checked():
    with patch.object(da, "_osv_request", return_value={"vulns": []}):
        vulns, status = da._query_osv("flask", "3.0.3")

    assert vulns == []
    assert status == "checked"


def test_a_failed_request_is_unreachable():
    with patch.object(da, "_osv_request", side_effect=OSError("dns")):
        vulns, status = da._query_osv("flask", "3.0.3")

    assert vulns == []
    assert status == "unreachable"


def test_a_failed_lookup_is_not_cached():
    """One blip must not report the package clean for the next 24 hours."""
    with patch.object(da, "_osv_request", side_effect=OSError("dns")) as failing:
        da._query_osv("flask", "3.0.3")
        assert failing.call_count == 1

    with patch.object(da, "_osv_request", return_value={"vulns": []}) as ok:
        vulns, status = da._query_osv("flask", "3.0.3")

    assert ok.call_count == 1, "the failure was cached and suppressed the retry"
    assert status == "checked"


def test_a_successful_lookup_is_still_cached():
    with patch.object(da, "_osv_request", return_value={"vulns": []}) as ok:
        da._query_osv("flask", "3.0.3")
        da._query_osv("flask", "3.0.3")

    assert ok.call_count == 1


# ----------------------------------------------------------
# The status reaches the report
# ----------------------------------------------------------

def test_every_dependency_carries_a_lookup_status():
    with patch.object(da, "_osv_request", return_value={"vulns": []}), \
         patch.object(da, "_fetch_latest_pypi_version", return_value=None):
        deps = _analyze({"requirements.txt": "flask==3.0.3\nrequests\n"})

    assert {d["vuln_lookup"] for d in deps.values()} <= {
        "checked", "unreachable", "skipped"}
    assert all("vuln_lookup" in d for d in deps.values())


def test_an_unpinned_dependency_is_skipped_not_checked():
    """Nothing was asked, so nothing may be implied."""
    with patch.object(da, "_osv_request", return_value={"vulns": []}), \
         patch.object(da, "_fetch_latest_pypi_version", return_value=None):
        deps = _analyze({"requirements.txt": "requests\n"})

    assert deps["requests"]["vuln_lookup"] == "skipped"


def test_a_pinned_dependency_with_a_live_lookup_is_checked():
    with patch.object(da, "_osv_request", return_value={"vulns": []}), \
         patch.object(da, "_fetch_latest_pypi_version", return_value=None):
        deps = _analyze({"requirements.txt": "flask==3.0.3\n"})

    assert deps["flask"]["vuln_lookup"] == "checked"


def test_a_down_lookup_is_reported_as_unreachable_not_clean():
    """The headline case: zero findings because the service was down."""
    with patch.object(da, "_osv_request", side_effect=OSError("timeout")), \
         patch.object(da, "_fetch_latest_pypi_version", return_value=None):
        deps = _analyze({"requirements.txt": "flask==3.0.3\n"})

    assert deps["flask"]["vulnerabilities"] == []
    assert deps["flask"]["vuln_lookup"] == "unreachable"


def test_node_dependencies_carry_the_status_too():
    with patch.object(da, "_osv_request", side_effect=OSError("timeout")):
        deps = _analyze({
            "package.json": '{"dependencies": {"lodash": "4.17.20"}}',
        })

    assert deps["lodash"]["vuln_lookup"] == "unreachable"
