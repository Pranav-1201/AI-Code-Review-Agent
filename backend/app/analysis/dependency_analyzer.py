# ==========================================================
# File: dependency_analyzer.py
# Purpose: Extract repository dependencies from multiple
#          package manager formats
# ==========================================================

import os
import re
import json


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
                "latest_version": version.strip() if version else "unknown",
                "is_outdated": False,
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

    return dependencies