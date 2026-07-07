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
# Main Analyzer
# ----------------------------------------------------------

def analyze_dependencies(repo_path):

    dependencies = []
    seen = set()  # Deduplicate by (name, type)

    requirements = os.path.join(repo_path, "requirements.txt")
    package_json = os.path.join(repo_path, "package.json")
    pyproject = os.path.join(repo_path, "pyproject.toml")
    pipfile = os.path.join(repo_path, "Pipfile")
    setup_py = os.path.join(repo_path, "setup.py")
    setup_cfg = os.path.join(repo_path, "setup.cfg")

    def _add_dep(name, version="unknown", dep_type="python"):
        key = (name.strip().lower(), dep_type)
        if key not in seen and name.strip():
            seen.add(key)
            dependencies.append({
                "name": name.strip(),
                "version": version.strip() if version else "unknown",
                "latest_version": "unknown",   # enriched below
                "is_outdated": False,           # enriched below
                "risk_level": "Low",
                "vulnerabilities": [],
                "type": dep_type
            })

    # -------------------------------------
    # Python dependencies (requirements.txt)
    # -------------------------------------

    if os.path.exists(requirements):

        try:
            with open(requirements, "r", encoding="utf-8", errors="ignore") as f:

                for line in f:

                    line = line.strip()

                    # Skip empty lines, comments, flags
                    if not line or line.startswith("#") or line.startswith("-"):
                        continue

                    # Handle various version specifiers
                    # name==version, name>=version, name~=version, name[extra]==version
                    match = re.match(r'^([a-zA-Z0-9_\-\.]+(?:\[[^\]]+\])?)\s*([><=!~]+\s*[\d\.\*]+)?', line)
                    if match:
                        name = re.sub(r'\[.*\]', '', match.group(1))  # Remove extras
                        version = match.group(2) or "unknown"
                        version = re.sub(r'[><=!~]+\s*', '', version).strip()
                        _add_dep(name, version, "python")
        except Exception:
            pass

    # -------------------------------------
    # Node dependencies (package.json)
    # -------------------------------------

    if os.path.exists(package_json):

        try:
            with open(package_json, "r", encoding="utf-8", errors="ignore") as f:

                data = json.load(f)

                # Regular dependencies
                deps = data.get("dependencies", {})
                for name, version in deps.items():
                    clean_version = re.sub(r'^[\^~>=<]+', '', version)
                    _add_dep(name, clean_version, "node")

                # Dev dependencies
                dev_deps = data.get("devDependencies", {})
                for name, version in dev_deps.items():
                    clean_version = re.sub(r'^[\^~>=<]+', '', version)
                    _add_dep(name, clean_version, "node-dev")

        except Exception:
            pass

    # -------------------------------------
    # Python dependencies (pyproject.toml)
    # -------------------------------------

    if os.path.exists(pyproject):

        try:
            with open(pyproject, "r", encoding="utf-8", errors="ignore") as f:

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

                        # Extract package name and version from quoted string
                        dep_match = re.match(r'["\']([a-zA-Z0-9_\-\.]+)(?:\[.*\])?\s*(?:([><=!~]+)\s*([\d\.\*]+))?["\']', stripped)
                        if dep_match:
                            name = dep_match.group(1)
                            version = dep_match.group(3) or "unknown"
                            _add_dep(name, version, "python")

                # Fallback: regex for "name==version" patterns anywhere
                matches = re.findall(r'"([a-zA-Z0-9_\-\.]+)==([^"]+)"', content)
                for name, version in matches:
                    _add_dep(name, version, "python")

                # Also match "name>=version" patterns
                matches = re.findall(r'"([a-zA-Z0-9_\-\.]+)>=([^"]+)"', content)
                for name, version in matches:
                    _add_dep(name, version, "python")

        except Exception:
            pass

    # -------------------------------------
    # Python dependencies (Pipfile)
    # -------------------------------------

    if os.path.exists(pipfile):

        try:
            with open(pipfile, "r", encoding="utf-8", errors="ignore") as f:

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
                            name = match.group(1)
                            version = match.group(2)
                            version = re.sub(r'[><=!~]+', '', version).strip()
                            if version == "*":
                                version = "latest"
                            _add_dep(name, version, "python")

        except Exception:
            pass

    # -------------------------------------
    # Python dependencies (setup.py)
    # -------------------------------------

    if os.path.exists(setup_py):

        try:
            with open(setup_py, "r", encoding="utf-8", errors="ignore") as f:

                content = f.read()

                # Match install_requires list items
                matches = re.findall(r'["\']([a-zA-Z0-9_\-\.]+)(?:[><=!~]+[\d\.]+)?["\']', content)
                for name in matches:
                    # Skip common non-package strings
                    if name not in ("python", "setup", "find_packages", "setuptools"):
                        _add_dep(name, "unknown", "python")

        except Exception:
            pass

    # -------------------------------------
    # Python dependencies (setup.cfg)
    # -------------------------------------

    if os.path.exists(setup_cfg):

        try:
            with open(setup_cfg, "r", encoding="utf-8", errors="ignore") as f:

                content = f.read()
                in_install = False

                for line in content.splitlines():
                    stripped = line.strip()

                    if "install_requires" in stripped:
                        in_install = True
                        continue

                    if in_install:
                        if stripped.startswith("[") or (stripped and "=" in stripped and not stripped[0].isspace()):
                            in_install = False
                            continue

                        match = re.match(r'^([a-zA-Z0-9_\-\.]+)(?:\s*[><=!~]+\s*([\d\.]+))?', stripped)
                        if match and match.group(1):
                            name = match.group(1)
                            version = match.group(2) or "unknown"
                            _add_dep(name, version, "python")

        except Exception:
            pass

    # --------------------------------------------------
    # PyPI Version Enrichment
    # --------------------------------------------------
    # For every Python dependency with a known pinned version,
    # fetch the current latest version from PyPI and determine
    # whether the pinned version is outdated.
    #
    # - Node packages are skipped here (npm audit is Phase 4)
    # - Packages with version "unknown" / "latest" / "*" are
    #   skipped because there is nothing meaningful to compare
    # - Network failures are silently ignored — the dependency
    #   is still reported, just without is_outdated data
    # --------------------------------------------------

    for dep in dependencies:

        # Only enrich Python packages for now
        if dep["type"] not in ("python",):
            continue

        # Skip unpinned or placeholder versions
        if dep["version"] in ("unknown", "latest", "*", ""):
            continue

        latest = _fetch_latest_pypi_version(dep["name"])

        if latest:
            dep["latest_version"] = latest
            dep["is_outdated"] = _is_version_outdated(dep["version"], latest)

            # Upgrade risk level for outdated packages so the
            # frontend can surface them with appropriate prominence
            if dep["is_outdated"]:
                dep["risk_level"] = "Medium"

    return dependencies