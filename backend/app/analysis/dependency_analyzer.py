# ==========================================================
# File: dependency_analyzer.py
# Purpose: Extract repository dependencies from multiple
#          package manager formats and check for outdated
#          versions against the PyPI JSON API.
# ==========================================================

import os
import re
import json
import time
import urllib.request
import urllib.error
from typing import Optional


# ----------------------------------------------------------
# PyPI Version Cache
# ----------------------------------------------------------
# In-memory cache keyed by lowercase package name.
# Each entry: {"latest": "1.2.3", "fetched_at": <timestamp>}
# TTL of 1 hour prevents redundant network calls within
# a single server session while keeping data reasonably fresh.
# ----------------------------------------------------------

_PYPI_VERSION_CACHE: dict = {}
_CACHE_TTL_SECONDS = 3600  # 1 hour


# ----------------------------------------------------------
# PyPI Helpers
# ----------------------------------------------------------

def _fetch_latest_pypi_version(package_name: str) -> Optional[str]:
    """
    Fetch the latest published version of a Python package
    from the PyPI JSON API (https://pypi.org/pypi/{name}/json).

    Returns the version string on success, or None if:
    - the package does not exist on PyPI
    - the network call fails or times out
    - the response cannot be parsed

    Results are cached in _PYPI_VERSION_CACHE for _CACHE_TTL_SECONDS
    to avoid hammering the API when many packages share a repo.
    """

    name_lower = package_name.lower().strip()
    if not name_lower:
        return None

    # Return cached value if still within TTL
    cached = _PYPI_VERSION_CACHE.get(name_lower)
    if cached and (time.time() - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
        return cached["latest"]

    try:
        url = f"https://pypi.org/pypi/{name_lower}/json"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "et-code-analyzer/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            latest = data["info"]["version"]

            # Store in cache
            _PYPI_VERSION_CACHE[name_lower] = {
                "latest": latest,
                "fetched_at": time.time()
            }
            return latest

    except Exception:
        # Network failure, package not found, or JSON parse error —
        # all handled silently so analysis continues uninterrupted
        return None


def _is_version_outdated(current: str, latest: str) -> bool:
    """
    Compare two version strings using PEP 440 semantics.
    Returns True if current is strictly older than latest.

    Primary: uses the `packaging` library for correct PEP 440
    comparisons (handles pre-releases, post-releases, epochs).

    Fallback: simple string inequality if `packaging` is not
    installed — not semantically perfect but never crashes.
    """

    if not current or not latest:
        return False

    # Version strings that cannot be compared meaningfully
    if current in ("unknown", "latest", "*", ""):
        return False

    try:
        from packaging.version import Version
        return Version(current) < Version(latest)
    except Exception:
        # Fallback: treat any version mismatch as potentially outdated
        return current.strip() != latest.strip()


# ----------------------------------------------------------
# OSV.dev vulnerability lookup (24h cache)
# ----------------------------------------------------------
# Queries the Open Source Vulnerabilities database
# (https://api.osv.dev/v1/query) for known CVEs affecting a pinned
# package version. Cached for 24h and silent on failure, so a network
# blip never breaks dependency analysis.

_OSV_CACHE: dict = {}
_OSV_TTL_SECONDS = 86400  # 24 hours


def _osv_severity(vuln: dict) -> str:
    ds = vuln.get("database_specific", {})
    if isinstance(ds, dict) and ds.get("severity"):
        return str(ds["severity"]).title()
    if isinstance(vuln.get("severity"), list) and vuln["severity"]:
        return "High"   # a CVSS vector is present — treat as High by default
    return "Unknown"


def _osv_request(name: str, version: str, ecosystem: str) -> dict:
    """POST one query to OSV and return the decoded response.

    Split out from _query_osv so the network boundary is one seam: failures
    raise here and are classified there, and a test can drive both paths
    without reaching the network.
    """
    payload = json.dumps({
        "version": version,
        "package": {"name": name, "ecosystem": ecosystem},
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.osv.dev/v1/query", data=payload,
        headers={"Content-Type": "application/json",
                 "User-Agent": "et-code-analyzer/1.0"},
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _query_osv(name: str, version: str, ecosystem: str = "PyPI") -> tuple:
    """Return ([{id, summary, severity}], status) for name@version.

    PHASE H / S5: the status is the point. This used to swallow every failure
    into an empty list, which the report then rendered exactly like a genuine
    all-clear — so an OSV outage read as "no known vulnerabilities" on every
    dependency in the project.

    A failed lookup is also NOT cached. It used to be, under a 24-hour TTL, so
    a single timeout would keep reporting the package clean for the rest of the
    day.
    """
    key = (ecosystem, name.lower().strip(), version.strip())
    cached = _OSV_CACHE.get(key)
    if cached and (time.time() - cached["fetched_at"]) < _OSV_TTL_SECONDS:
        return cached["vulns"], "checked"

    vulns: list = []
    try:
        data = _osv_request(name, version, ecosystem)
    except Exception:
        return [], "unreachable"

    for v in data.get("vulns", []) or []:
        vulns.append({
            "id": v.get("id", ""),
            "summary": v.get("summary") or (v.get("details", "") or "")[:160],
            "severity": _osv_severity(v),
        })

    _OSV_CACHE[key] = {"vulns": vulns, "fetched_at": time.time()}
    return vulns, "checked"


def _risk_from_vulns(vulns: list, current: str = "Low") -> str:
    """Any CVE -> at least High; a Critical-rated CVE -> Critical."""
    if not vulns:
        return current
    if any(str(v.get("severity", "")).lower() == "critical" for v in vulns):
        return "Critical"
    return "High"


# ----------------------------------------------------------
# npm version resolution
# ----------------------------------------------------------
# OSV answers "is THIS version vulnerable", but package.json records a RANGE,
# and `^` is npm's default. Asking about the floor of `^4.17.20` would report
# CVE-2021-23337 against a repo whose lockfile installs the patched 4.17.21 —
# a false positive on nearly every project. So we only ever query a version we
# actually know is installed: the lockfile first, then an exact pin. An
# unresolvable range is left unqueried rather than guessed at.

# "1.2.3", "v1.2.3", "1.2.3-beta.1" — one concrete version and nothing else.
_NPM_EXACT_RE = re.compile(r'^v?(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-+]+)?)$')


def _exact_npm_version(spec) -> Optional[str]:
    """Return the single version a package.json spec pins, else None.

    None means "this is a range, an alias, or a non-registry source" — i.e.
    the installed version is unknown from package.json alone.
    """
    if not spec:
        return None

    text = str(spec).strip()
    if text.startswith("="):
        text = text[1:].strip()

    match = _NPM_EXACT_RE.match(text)
    return match.group(1) if match else None


# PHASE H / S7: the Python counterpart of _exact_npm_version.
#
# The Python parsers used to strip the operator off a constraint and keep the
# digits, so `flask>=2.0` was recorded as version "2.0". A lower bound is not a
# version, and that invented value was then used as the OSV query key — the
# report listed CVEs against 2.0 for a project whose lockfile installs 3.0.3.
# The node side has refused to do this since Phase C; this is the same rule.
#
# PEP 440 exact-equality clause. `==1.4.*` is excluded on purpose: a wildcard
# pin still names a range, and no single version can be queried for it.
_PY_EXACT_RE = re.compile(r'^={2,3}\s*([0-9][^,;\s]*)$')


def _exact_python_version(spec) -> Optional[str]:
    """Return the single version a requirement specifier pins, else None.

    None means "range, wildcard, or absent" — the installed version is not
    knowable from this manifest alone, and a lockfile is the only honest way to
    find out.

    A compound specifier is accepted when exactly one of its clauses is an
    exact pin: `==3.11,<4` does pin 3.11, the `<4` merely restating it.
    """
    if not spec:
        return None

    for clause in str(spec).split(","):
        clause = clause.strip()
        if "*" in clause:
            continue
        match = _PY_EXACT_RE.match(clause)
        if match:
            return match.group(1).strip()

    return None


# PHASE H / S6: the Python counterpart of _npm_locked_versions.
#
# After S7 an unpinned requirement honestly resolves to "unknown". That is
# better than inventing a number, but unhelpful when the real answer is sitting
# in a lockfile beside the manifest — and it is the lockfile, not the range,
# that says which version OSV should be asked about.
_PY_LOCK_REQUIREMENT_RE = re.compile(
    r'^([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s;#]+)')

# uv.lock and poetry.lock are both TOML with an array of [[package]] tables
# carrying `name` and `version`. Parsed by scanning rather than with a TOML
# reader: tomllib is 3.11+ only and the analysis layer is deliberately
# dependency-free (DECISIONS D1).
_PY_LOCK_TOML_NAME_RE = re.compile(r'^name\s*=\s*["\']([^"\']+)["\']')
_PY_LOCK_TOML_VERSION_RE = re.compile(r'^version\s*=\s*["\']([^"\']+)["\']')


def _normalise_project_name(name: str) -> str:
    """PEP 503 normalisation: flit_core, flit-core and Flit.Core are one project."""
    return re.sub(r'[-_.]+', '-', str(name).strip()).lower()


def _python_locked_versions(repo_path: str) -> dict:
    """Map normalised project name -> exact installed version from a lockfile.

    Reads requirements.lock (pip-compile style) and the [[package]] tables of
    uv.lock and poetry.lock. A missing or unreadable lockfile yields {} and the
    caller simply learns nothing, which is the correct failure mode here.
    """
    locked: dict = {}

    for filename in ("requirements.lock", "uv.lock", "poetry.lock"):
        path = os.path.join(repo_path, filename)
        if not os.path.exists(path):
            continue

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                content = handle.read()
        except OSError:
            continue

        if filename == "requirements.lock":
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith(("#", "-")):
                    continue
                match = _PY_LOCK_REQUIREMENT_RE.match(line)
                if match:
                    locked.setdefault(_normalise_project_name(match.group(1)),
                                      match.group(2).strip())
            continue

        # TOML: a name and the first version that follows it, reset at each
        # [[package]] boundary so a stray top-level `version = 1` (uv.lock
        # opens with exactly that) cannot be attached to a package.
        pending_name = None
        for line in content.splitlines():
            line = line.strip()

            if line.startswith("[["):
                pending_name = None
                continue
            if line.startswith("["):
                pending_name = None
                continue

            name_match = _PY_LOCK_TOML_NAME_RE.match(line)
            if name_match:
                pending_name = _normalise_project_name(name_match.group(1))
                continue

            version_match = _PY_LOCK_TOML_VERSION_RE.match(line)
            if version_match and pending_name:
                locked.setdefault(pending_name, version_match.group(1).strip())
                pending_name = None

    return locked


def _npm_locked_versions(repo_path: str) -> dict:
    """Map package name -> exact installed version from package-lock.json.

    Only DIRECT installs are returned: a `node_modules/x/node_modules/y` entry
    is a second copy of y pinned for x, so letting it win would report a CVE
    against a version the app does not itself depend on. A missing or corrupt
    lockfile yields {} — callers fall back to exact pins.
    """
    try:
        with open(os.path.join(repo_path, "package-lock.json"),
                  "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    versions: dict = {}

    # lockfileVersion 2/3: flat "packages" map keyed by install path.
    packages = data.get("packages")
    if isinstance(packages, dict):
        for path, meta in packages.items():
            if not isinstance(path, str) or not path.startswith("node_modules/"):
                continue
            name = path[len("node_modules/"):]
            if "node_modules/" in name:      # nested copy, not a direct install
                continue
            version = meta.get("version") if isinstance(meta, dict) else None
            if name and version:
                versions[name] = str(version)

    # lockfileVersion 1: "dependencies" map keyed by name. v2 carries both, and
    # the "packages" map is authoritative there, so v1 only fills the gaps.
    legacy = data.get("dependencies")
    if isinstance(legacy, dict):
        for name, meta in legacy.items():
            version = meta.get("version") if isinstance(meta, dict) else None
            if name and version:
                versions.setdefault(name, str(version))

    return versions


# ----------------------------------------------------------
# Main Analyzer
# ----------------------------------------------------------

# ----------------------------------------------------------
# B1: one manifest parser per function
# ----------------------------------------------------------
# `analyze_dependencies` was 385 lines and CC 68 — six inlined manifest
# parsers, a nested recorder, and an enrichment pass, all in one body. The
# parsers never enrich and the enrichers never parse, so they split cleanly.
#
# Every parser is fail-soft by contract: a malformed manifest costs you that
# manifest's dependencies, never the scan. That is why each keeps its own
# bare `except Exception`, rather than one try wrapping the whole table.
# ----------------------------------------------------------

class _DependencyCollector:
    """Accumulates dependencies, deduplicating by (lowercased name, type).

    First write wins, which is why the order parsers run in is part of the
    contract: whichever manifest is read first owns the version for a package
    declared in two of them.
    """

    def __init__(self):
        self.dependencies = []
        self.seen = set()

    def add(self, name, version="unknown", dep_type="python", constraint=""):
        """Record a dependency.

        PHASE H / S7: `version` holds a concrete version or "unknown", never a
        constraint. Callers that only have a specifier pass it as `constraint`
        and leave `version` alone; resolution happens here so no parser can
        break the invariant on its own. `version_source` says how the value was
        arrived at, so a reader can tell a pin from a guess.
        """
        key = (name.strip().lower(), dep_type)
        if key in self.seen or not name.strip():
            return

        self.seen.add(key)

        constraint = (constraint or "").strip()
        version = (version or "unknown").strip() or "unknown"

        if version != "unknown":
            source = "pinned"
        elif constraint:
            source = "unpinned"
        else:
            source = "unspecified"

        self.dependencies.append({
            "name": name.strip(),
            "version": version,
            "constraint": constraint,
            "version_source": source,
            # PHASE H / S5: how the vulnerability lookup went — "checked",
            # "unreachable" or "skipped". Defaults to skipped so a dependency
            # the enrichment loop never reaches cannot read as clean.
            "vuln_lookup": "skipped",
            "latest_version": "unknown",   # enriched below
            "is_outdated": False,           # enriched below
            "risk_level": "Low",
            "vulnerabilities": [],
            "type": dep_type
        })


def _parse_requirements_txt(path, add):
    """requirements.txt — one specifier per line, flags and comments skipped."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:

            for line in f:

                line = line.strip()

                # Skip empty lines, comments, flags
                if not line or line.startswith("#") or line.startswith("-"):
                    continue

                # Handle various version specifiers
                # name==version, name>=version, name~=version, name[extra]==version
                # PHASE H / S7: capture the WHOLE specifier, not just its
                # first clause, and resolve it rather than stripping the
                # operator off and keeping the digits. `flask>=2.0` used to
                # be recorded as version "2.0".
                match = re.match(
                    r'^([a-zA-Z0-9_\-\.]+(?:\[[^\]]+\])?)\s*([^;#]*)', line)
                if match:
                    name = re.sub(r'\[.*\]', '', match.group(1))  # Remove extras
                    constraint = (match.group(2) or "").strip()
                    add(name,
                        _exact_python_version(constraint) or "unknown",
                        "python",
                        constraint)
    except Exception:
        pass


def _parse_package_json(path, add, node_specs):
    """package.json — both dependency blocks, typed apart for the report.

    `node_specs` keeps the UNMANGLED spec: `add` stores a display version with
    the range operator stripped, which makes "^1.2.3" indistinguishable from
    the exact pin "1.2.3" — a distinction the OSV lookup depends on.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:

            data = json.load(f)

            # Regular dependencies
            deps = data.get("dependencies", {})
            for name, version in deps.items():
                clean_version = re.sub(r'^[\^~>=<]+', '', str(version))
                add(name, clean_version, "node")
                node_specs.setdefault(name.strip().lower(), str(version))

            # Dev dependencies
            dev_deps = data.get("devDependencies", {})
            for name, version in dev_deps.items():
                clean_version = re.sub(r'^[\^~>=<]+', '', str(version))
                add(name, clean_version, "node-dev")
                node_specs.setdefault(name.strip().lower(), str(version))

    except Exception:
        pass


def _parse_pyproject_toml(path, add):
    """pyproject.toml — the [project] dependencies list, then a whole-file
    fallback for quoted requirements anywhere else (build-system, and the
    many tools that keep their own lists)."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:

            content = f.read()

            # Try to find [project] dependencies section
            # Matches: "package>=1.0", "package==1.0", "package~=1.0", "package"
            in_deps = False
            for line in content.splitlines():
                stripped = line.strip()

                if stripped.startswith("dependencies") and "=" in stripped:
                    in_deps = True
                    continue

                if in_deps:
                    if stripped == "]":
                        in_deps = False
                        continue

                    # PHASE H / S7: take the whole specifier out of the
                    # quoted string and resolve it, rather than capturing
                    # one operator and one run of digits.
                    dep_match = re.match(
                        r'''["']([a-zA-Z0-9_\-\.]+)(?:\[[^\]]*\])?\s*([^"';]*)''',
                        stripped)
                    if dep_match:
                        name = dep_match.group(1)
                        constraint = (dep_match.group(2) or "").strip()
                        add(name,
                            _exact_python_version(constraint) or "unknown",
                            "python",
                            constraint)

            # Fallback: any quoted "name<specifier>" anywhere in the file.
            #
            # This is where `"flit_core==3.11,<4"` became version
            # "3.11,<4" — the old pattern captured everything up to the
            # closing quote and stored it verbatim in a version field.
            for name, constraint in re.findall(
                    r'"([a-zA-Z0-9_\-\.]+)\s*((?:[><=!~]=?|===)[^"]*)"', content):
                constraint = constraint.strip()
                add(name,
                    _exact_python_version(constraint) or "unknown",
                    "python",
                    constraint)

    except Exception:
        pass


def _parse_pipfile(path, add):
    """Pipfile — [packages] and [dev-packages]; any other section closes both.

    Both land as type "python": the Pipfile dev/prod split is not carried into
    the report the way package.json's is.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:

            content = f.read()
            in_packages = False
            in_dev = False

            for line in content.splitlines():
                stripped = line.strip()

                if stripped == "[packages]":
                    in_packages = True
                    in_dev = False
                    continue
                elif stripped == "[dev-packages]":
                    in_packages = False
                    in_dev = True
                    continue
                elif stripped.startswith("["):
                    in_packages = False
                    in_dev = False
                    continue

                if in_packages or in_dev:
                    # Format: package_name = "==1.0.0" or package_name = "*"
                    match = re.match(r'^([a-zA-Z0-9_\-\.]+)\s*=\s*["\']([^"\']*)["\']', stripped)
                    if match:
                        # PHASE H / S7: the operator carried meaning and
                        # was being deleted — `">=2.0"` became "2.0".
                        name = match.group(1)
                        constraint = (match.group(2) or "").strip()
                        add(name,
                            _exact_python_version(constraint) or "unknown",
                            "python",
                            constraint)

    except Exception:
        pass


def _parse_setup_py(path, add):
    """setup.py — names only.

    setup.py is executable Python; this reads it as text rather than running
    it, so a version attached to a name is not reliably recoverable and every
    dependency here is recorded as unspecified.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:

            content = f.read()

            # Match install_requires list items
            matches = re.findall(r'["\']([a-zA-Z0-9_\-\.]+)(?:[><=!~]+[\d\.]+)?["\']', content)
            for name in matches:
                # Skip common non-package strings
                if name not in ("python", "setup", "find_packages", "setuptools"):
                    add(name, "unknown", "python")

    except Exception:
        pass


def _parse_setup_cfg(path, add):
    """setup.cfg — the indented install_requires block."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:

            content = f.read()
            in_install = False

            for line in content.splitlines():
                stripped = line.strip()

                if "install_requires" in stripped:
                    in_install = True
                    continue

                if in_install:
                    if not stripped:
                        continue

                    # PHASE H / S7: the continuation test has to look at
                    # the ORIGINAL line's indentation. `stripped` has
                    # already had it removed, so `stripped[0].isspace()`
                    # was always False — and since every versioned
                    # requirement contains "=", `flask>=2.0` closed the
                    # section on its own first line and no setup.cfg
                    # dependency with a version was ever recorded.
                    if stripped.startswith("[") or not line[:1].isspace():
                        in_install = False
                        continue

                    match = re.match(
                        r'^([a-zA-Z0-9_\-\.]+(?:\[[^\]]*\])?)\s*([^;#]*)', stripped)
                    if match and match.group(1):
                        name = re.sub(r'\[.*\]', '', match.group(1))
                        constraint = (match.group(2) or "").strip()
                        add(name,
                            _exact_python_version(constraint) or "unknown",
                            "python",
                            constraint)

    except Exception:
        pass


# ----------------------------------------------------------
# B1: version + vulnerability enrichment
# ----------------------------------------------------------
# Python: fetch the latest version from PyPI to flag outdated pins, then ask
# OSV about the pinned version.
#
# Node: OSV only (no registry "latest" lookup yet). The version asked about is
# the one actually installed — see _npm_locked_versions/_exact_npm_version for
# why a bare range is skipped instead of guessed.
#
# Packages with version "unknown" / "latest" / "*" have nothing meaningful to
# compare. Network failures are silent: the dependency is still reported, just
# without enrichment.
#
# Each enricher writes its own vulnerabilities/risk_level rather than handing
# them back to a shared tail. The inlined version reached that tail via
# `continue`, so a returned value would have to reproduce the skip exactly;
# owning the write is simpler and provably equivalent.
# ----------------------------------------------------------

def _record_vulnerabilities(dep, vulns):
    """Apply an OSV result to a dependency. No result, no change."""
    if vulns:
        dep["vulnerabilities"] = vulns
        dep["risk_level"] = _risk_from_vulns(vulns, current=dep["risk_level"])


def _resolve_python_versions_from_lockfile(dependencies, repo_path):
    """PHASE H / S6: fill unresolved Python versions from a lockfile.

    Runs before any enrichment, so the PyPI and OSV lookups ask about the
    version that is actually installed rather than skipping the dependency
    entirely.

    Unknowns only. A lockfile disagreeing with an exact pin is a conflict
    between two manifests, and resolving that silently would hide it.
    """
    py_locked = _python_locked_versions(repo_path)
    if not py_locked:
        return

    for dep in dependencies:
        if dep["type"] != "python" or dep["version"] != "unknown":
            continue
        resolved = py_locked.get(_normalise_project_name(dep["name"]))
        if resolved:
            dep["version"] = resolved
            dep["version_source"] = "lockfile"


def _enrich_python_dependency(dep):
    """Latest release, outdated flag, and the OSV lookup for one package."""

    # PHASE H: "what is the newest release of this package" is answerable
    # whether or not the installed version is known, so the PyPI lookup runs
    # unconditionally. It used to sit behind the unknown-version guard below,
    # which meant an honestly-unpinned dependency lost its latest_version too —
    # flask pins nothing and ships no lockfile, so all 8 of its dependencies
    # showed no upgrade target at all.
    latest = _fetch_latest_pypi_version(dep["name"])
    if latest:
        dep["latest_version"] = latest

    # Everything past here needs a concrete version to compare or query.
    # PHASE H / S5: "skipped" is already the default and is the honest answer —
    # nothing was asked, so nothing about this package's safety may be implied.
    known_version = dep["version"] not in ("unknown", "latest", "*", "")
    if not known_version:
        return

    if latest:
        dep["is_outdated"] = _is_version_outdated(dep["version"], latest)

        # Upgrade risk level for outdated packages so the frontend can surface
        # them with appropriate prominence
        if dep["is_outdated"]:
            dep["risk_level"] = "Medium"

    # OSV.dev CVE lookup — known vulnerabilities for the PINNED version take
    # precedence over the outdated-only heuristic above.
    vulns, dep["vuln_lookup"] = _query_osv(
        dep["name"], dep["version"], ecosystem="PyPI")
    _record_vulnerabilities(dep, vulns)


def _enrich_node_dependency(dep, npm_locked, node_specs):
    """OSV lookup for one npm package, against the version really installed."""

    installed = (npm_locked.get(dep["name"])
                 or _exact_npm_version(node_specs.get(dep["name"].lower())))
    if not installed:
        return

    # Report the version the lookup was actually performed against, so a CVE
    # the reader is shown can be checked against the version the reader is
    # shown. Otherwise `^4.17.20` displays as 4.17.20 beside a CVE looked up
    # for the installed 4.17.21.
    dep["version"] = installed

    vulns, dep["vuln_lookup"] = _query_osv(
        dep["name"], installed, ecosystem="npm")
    _record_vulnerabilities(dep, vulns)


def _read_if_present(repo_path, filename, parse, *args):
    """Run `parse` over `filename` if the repository has one."""
    path = os.path.join(repo_path, filename)
    if os.path.exists(path):
        parse(path, *args)


def analyze_dependencies(repo_path):
    """Every declared dependency of `repo_path`, enriched and deduplicated."""

    collector = _DependencyCollector()
    add = collector.add

    # Raw package.json specs, keyed by lowercase name — see _parse_package_json.
    node_specs: dict = {}

    # ORDER IS PART OF THE CONTRACT. `add` dedupes on first write, so this
    # decides which manifest owns a package declared in two of them. This is
    # the order the inlined blocks ran in; do not sort or regroup it.
    _read_if_present(repo_path, "requirements.txt", _parse_requirements_txt, add)
    _read_if_present(repo_path, "package.json", _parse_package_json, add, node_specs)
    _read_if_present(repo_path, "pyproject.toml", _parse_pyproject_toml, add)
    _read_if_present(repo_path, "Pipfile", _parse_pipfile, add)
    _read_if_present(repo_path, "setup.py", _parse_setup_py, add)
    _read_if_present(repo_path, "setup.cfg", _parse_setup_cfg, add)

    dependencies = collector.dependencies

    npm_locked = _npm_locked_versions(repo_path)
    _resolve_python_versions_from_lockfile(dependencies, repo_path)

    for dep in dependencies:
        if dep["type"] == "python":
            _enrich_python_dependency(dep)
        elif dep["type"] in ("node", "node-dev"):
            _enrich_node_dependency(dep, npm_locked, node_specs)

    return dependencies
