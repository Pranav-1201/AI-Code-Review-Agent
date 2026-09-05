# B1 — Decompose `analyze_dependencies` and `review_repository`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Break the two functions that produce the entire report shape into
named, independently testable pieces, with **zero change to the bytes they
produce**.

**Architecture:** Pure extraction. Every extracted helper is module-level and
takes explicit arguments — no closures, no new state, no reordering of work.
The two entry points become orchestration: read top to bottom, each line a
named phase. Additive checkpoints throughout (CONSTRAINTS §16): the helper is
added and the suite is green *before* the inlined code is deleted, in the same
commit, so the tree never goes red.

**Tech Stack:** Python 3.11 (`venv/Scripts/python.exe`), pytest, stdlib only —
**no new runtime dependency** (CONSTRAINTS §7).

**Spec:** `docs/STAFF_AUDIT_2026-08-19.md` line 206 (B1, unassigned backlog),
and `docs/HANDOVER.md` §1b "What is genuinely left", which is why this was
deferred rather than half-done.

---

## Global Constraints

- **No behaviour change.** Not "no intended change" — byte-identical output,
  proven by the gate below. If a defect is found along the way it is recorded
  and fixed in a **separate commit** with its own test, never folded into an
  extraction commit.
- **CONSTRAINTS §16 — additive checkpoints.** New code verified green before
  old code is removed. The tree never goes red between commits.
- **CONSTRAINTS §9 — one logical change per commit.** Stage explicit paths.
  **Never `git add -A`** (CONSTRAINTS §2).
- **CONSTRAINTS §7 — no new runtime dependency.** The analysis layer is
  deliberately stdlib-only.
- **CONSTRAINTS §1 — no AI attribution** in any commit message.
- **CONSTRAINTS §11 — never lower a benchmark threshold** to make the gate pass.
- Interpreter is `venv/Scripts/python.exe`. Never bare `python`.
- Helpers are **private** (`_` prefix) and **module-level**. `review_repository`
  keeps its `self` only for `self.refactor_engine`; nothing extracted needs it.

---

## The gate (this is what makes the refactor safe)

`scratchpad/b1_baseline.py` runs both functions over **this repository** — 247
files — with the two network calls stubbed, and dumps canonical JSON.

Measured before starting, this session:

| | |
|---|---|
| Two consecutive runs | **byte-identical** (`cmp` clean) |
| Size | **5,429,674 bytes** |
| `dependencies` | 21 |
| `file_reports` | 247 |
| `issues` | 97 |
| `health_score` | 65 |
| `analyze_dependencies` | **385 lines, CC 68** |
| `review_repository` | **398 lines, CC 58** |

`before.json` is captured. **After every task**, `after.json` must `cmp` clean
against it. A single differing byte fails the task.

This is the primary safety net *because* it is real data, not a fixture — R3:
fixtures only catch what their author already imagined.

---

## File structure

**`backend/app/analysis/dependency_analyzer.py`** — one manifest parser per
function, then enrichment. Parsers never enrich; enrichment never parses.

| Function | Responsibility |
|---|---|
| `_DependencyCollector` | Owns `dependencies` + `seen`. Replaces the `_add_dep` closure; the version/constraint/`version_source` invariant lives here, unchanged. |
| `_parse_requirements_txt(path, add)` | requirements.txt |
| `_parse_package_json(path, add, node_specs)` | package.json, both dep blocks |
| `_parse_pyproject_toml(path, add)` | pyproject.toml, section scan + quoted fallback |
| `_parse_pipfile(path, add)` | Pipfile `[packages]` / `[dev-packages]` |
| `_parse_setup_py(path, add)` | setup.py `install_requires` |
| `_parse_setup_cfg(path, add)` | setup.cfg `install_requires` |
| `_resolve_python_versions_from_lockfile(deps, repo_path)` | S6 lockfile fill, unknowns only |
| `_enrich_python_dependency(dep)` | PyPI latest + outdated + OSV |
| `_enrich_node_dependency(dep, npm_locked, node_specs)` | installed version + OSV |
| `analyze_dependencies(repo_path)` | orchestration only |

**`backend/app/services/repository_review_engine.py`**

| Function | Responsibility |
|---|---|
| `_non_code_file_report(file_data)` | the minimal report for a non-code file |
| `_file_report_from_result(result)` | the file report for an analysed code file |
| `_Aggregates` / `_aggregate_results(results)` | one pass over results → reports, issues, prod/test split, counters |
| `_Averages` / `_compute_averages(results, prod_results)` | weighted score, doc, cyclomatic |
| `_HealthScore` / `_compute_health_score(...)` | the four dimensions and the composite |
| `_group_issues(all_issues)` | message-keyed grouping with `affected_files` |
| `_graph_centrality(dependency_graph, repo_data)` | most central file, most reused first-party module |
| `_maintainability_warnings(prod_results)` | long_file + complex_function warnings |
| `_build_insights(...)` | top critical issues, most complex files, centrality |
| `_attach_duplicates(file_reports, duplicates)` | duplicate map onto reports |
| `_architecture_summary(results)` | frameworks + architecture, both fail-soft |
| `RepositoryReviewEngine.review_repository` | orchestration only |

**`backend/tests/test_b1_contract.py`** — new. Characterization tests: a
synthetic repo carrying all six manifest types and a handful of code files,
asserting the exact structures both functions produce. Fast enough for CI,
unlike the 247-file gate.

---

## A note on "watch it fail"

These are **characterization** tests, not TDD tests: they describe behaviour
that already exists, so they pass on first run against unmodified code. A test
that has never been red proves nothing (R3). So each characterization task has
an explicit **perturbation step**: break the function on purpose, watch the new
test go red, revert. That is what earns the test its place.

---

### Task 1: Characterize `analyze_dependencies`

**Files:**
- Create: `backend/tests/test_b1_contract.py`
- Test: the same file

**Interfaces:**
- Consumes: `backend.app.analysis.dependency_analyzer.analyze_dependencies`
- Produces: `_write_manifest_repo(tmp_path)` — a pytest helper other tasks
  reuse; writes requirements.txt, package.json, pyproject.toml, Pipfile,
  setup.py and setup.cfg into `tmp_path` and returns `str(tmp_path)`.

- [ ] **Step 1: Write the characterization test**

Covering, for each of the six manifests, that the parser is reached and the
`version` / `constraint` / `version_source` invariant holds — the invariant
Phase H established and this refactor must not disturb.

```python
import json
import pytest
from backend.app.analysis import dependency_analyzer as da


def _write_manifest_repo(tmp_path):
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
    """Enrichment is not what these tests are about."""
    monkeypatch.setattr(da, "_fetch_latest_pypi_version", lambda name: None)
    monkeypatch.setattr(da, "_query_osv",
                        lambda name, version, ecosystem="PyPI": ([], "checked"))


@pytest.fixture
def deps(tmp_path, no_network):
    return {d["name"].lower(): d
            for d in da.analyze_dependencies(_write_manifest_repo(tmp_path))}


def test_every_manifest_is_read(deps):
    """One name from each of the six files."""
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
    """The continuation test read `stripped`, so this section always closed
    on its own first line and no versioned dep was ever recorded."""
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
```

- [ ] **Step 2: Run it — it must PASS against unmodified code**

Run: `venv/Scripts/python.exe -m pytest backend/tests/test_b1_contract.py -v`
Expected: all 9 PASS. A failure here means the test is wrong, not the code.

- [ ] **Step 3: Perturb, and watch it go red**

Temporarily change the `setup.cfg` continuation test in
`dependency_analyzer.py` from `not line[:1].isspace()` back to the old
`stripped[0].isspace()` bug. Run the test file again.
Expected: `test_setup_cfg_versioned_requirements_are_recorded` FAILS.
**Then revert the perturbation** (`git checkout -- <file>`) and re-run:
all 9 PASS again.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_b1_contract.py
git commit -F <message-file>
```
Message: `Characterize analyze_dependencies before decomposing it`

---

### Task 2: Extract the collector and the six manifest parsers

**Files:**
- Modify: `backend/app/analysis/dependency_analyzer.py:388-772`

**Interfaces:**
- Produces:
  - `class _DependencyCollector` with `.dependencies: list`, `.seen: set`,
    and `.add(name, version="unknown", dep_type="python", constraint="")`
  - `_parse_requirements_txt(path, add) -> None`
  - `_parse_package_json(path, add, node_specs) -> None`
  - `_parse_pyproject_toml(path, add) -> None`
  - `_parse_pipfile(path, add) -> None`
  - `_parse_setup_py(path, add) -> None`
  - `_parse_setup_cfg(path, add) -> None`
  - where `add` is `_DependencyCollector.add`, bound.

- [ ] **Step 1: Add `_DependencyCollector` above `analyze_dependencies`**

The body of `.add` is the current `_add_dep` body verbatim, with `seen` and
`dependencies` becoming `self.seen` and `self.dependencies`. Keep the
docstring — it explains the S7 invariant and is the reason this is safe.

- [ ] **Step 2: Add the six parsers above `analyze_dependencies`**

Each takes the manifest path and the `add` callable. Each body is the current
`if os.path.exists(...)` block's *contents*, verbatim, including the bare
`except Exception: pass` — preserving fail-soft parsing exactly. The
`os.path.exists` test stays in the caller so the parser list reads as a table.

- [ ] **Step 3: Rewrite the parsing half of `analyze_dependencies` to call them**

```python
    collector = _DependencyCollector()
    add = collector.add
    node_specs: dict = {}

    for filename, parse in (
        ("requirements.txt", _parse_requirements_txt),
        ("pyproject.toml",   _parse_pyproject_toml),
        ("Pipfile",          _parse_pipfile),
        ("setup.py",         _parse_setup_py),
        ("setup.cfg",        _parse_setup_cfg),
    ):
        path = os.path.join(repo_path, filename)
        if os.path.exists(path):
            parse(path, add)

    package_json = os.path.join(repo_path, "package.json")
    if os.path.exists(package_json):
        _parse_package_json(package_json, add, node_specs)

    dependencies = collector.dependencies
```

**Order matters and must not change:** requirements.txt, package.json,
pyproject.toml, Pipfile, setup.py, setup.cfg. `_add_dep` dedupes on first
write, so reordering silently changes which manifest wins a conflict. The
loop above puts package.json second by running it in its own statement — keep
that. If a reviewer prefers one table, the table must carry package.json in
position two with its extra argument.

- [ ] **Step 4: Verify — contract, suite, and the real-repo gate**

```bash
venv/Scripts/python.exe -m pytest backend/tests/test_b1_contract.py -q
venv/Scripts/python.exe -m pytest backend/tests -q
venv/Scripts/python.exe scratchpad/b1_baseline.py scratchpad/after.json
cmp scratchpad/before.json scratchpad/after.json && echo IDENTICAL
```
Expected: contract green; suite ≥ 500 passed, 0 failed; **`IDENTICAL`**.

- [ ] **Step 5: Commit**

Message: `Extract the six manifest parsers out of analyze_dependencies`

---

### Task 3: Extract lockfile resolution and enrichment

**Files:**
- Modify: `backend/app/analysis/dependency_analyzer.py`

**Interfaces:**
- Produces:
  - `_resolve_python_versions_from_lockfile(dependencies, repo_path) -> None`
    (mutates in place; unknowns only)
  - `_enrich_python_dependency(dep) -> None`
  - `_enrich_node_dependency(dep, npm_locked, node_specs) -> None`

- [ ] **Step 1: Extract the three helpers, bodies verbatim**

The `for dep in dependencies:` loop keeps its `if/elif/else` shape; only the
two branch bodies move out. The shared tail —

```python
        if vulns:
            dep["vulnerabilities"] = vulns
            dep["risk_level"] = _risk_from_vulns(vulns, current=dep["risk_level"])
```

— moves *into* each enricher, because `continue` in the current code skips it
and a returned `vulns` would have to reproduce that control flow exactly. Each
enricher therefore owns its own write. This is the one place where the shape
changes; the values do not, which the gate proves.

- [ ] **Step 2: Reduce the enrichment half of `analyze_dependencies` to**

```python
    npm_locked = _npm_locked_versions(repo_path)
    _resolve_python_versions_from_lockfile(dependencies, repo_path)

    for dep in dependencies:
        if dep["type"] == "python":
            _enrich_python_dependency(dep)
        elif dep["type"] in ("node", "node-dev"):
            _enrich_node_dependency(dep, npm_locked, node_specs)

    return dependencies
```

- [ ] **Step 3: Verify** — same four commands as Task 2 Step 4. `IDENTICAL`
      is required, and it is the only thing that proves the `vulns` control-flow
      move was faithful.

- [ ] **Step 4: Measure and record**

```bash
venv/Scripts/python.exe scratchpad/cc.py   # prints line count + CC per function
```
Expected: `analyze_dependencies` well under its starting **385 lines / CC 68**.

- [ ] **Step 5: Commit**

Message: `Extract lockfile resolution and version enrichment`

---

### Task 4: Characterize `review_repository`

**Files:**
- Modify: `backend/tests/test_b1_contract.py`

**Interfaces:**
- Consumes: `RepositoryReviewEngine`, `HeuristicRefactorEngine`
- Produces: `_repo_data()` — a synthetic `repo_data` list (one production
  file, one test file, one non-code file) reused by later tasks.

- [ ] **Step 1: Write the characterization test**

```python
from backend.app.analysis.heuristic_refactor_engine import HeuristicRefactorEngine
from backend.app.services.repository_review_engine import RepositoryReviewEngine


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


@pytest.fixture
def report(tmp_path):
    engine = RepositoryReviewEngine()
    engine.refactor_engine = HeuristicRefactorEngine()
    return engine.review_repository(str(tmp_path), _repo_data())


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


def test_every_file_report_carries_the_same_keys(report):
    keysets = {frozenset(f) for f in report["file_reports"]}
    assert len(keysets) == 1, "file reports disagree on their shape"


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
    engine = RepositoryReviewEngine()
    engine.refactor_engine = HeuristicRefactorEngine()
    empty = engine.review_repository(str(tmp_path), [])
    assert empty["repository_summary"]["health_score"] == 0
    assert empty["file_reports"] == []
    assert empty["insights"]["most_reused_module"] == "None"
```

- [ ] **Step 2: Run it — must PASS against unmodified code**

Run: `venv/Scripts/python.exe -m pytest backend/tests/test_b1_contract.py -v`
Expected: all 17 (9 + 8) PASS.

- [ ] **Step 3: Perturb, and watch it go red**

Temporarily change the health-score weight `0.35` to `0.45` in
`review_repository`. Run again.
Expected: `test_the_health_score_is_the_documented_weighted_composite` FAILS.
**Revert** and re-run: all 17 PASS.

- [ ] **Step 4: Commit**

Message: `Characterize review_repository before decomposing it`

---

### Task 5: Extract the two file-report builders

**Files:**
- Modify: `backend/app/services/repository_review_engine.py:596-993`

**Interfaces:**
- Produces:
  - `_non_code_file_report(file_data) -> Dict`
  - `_file_report_from_result(result) -> Dict`

- [ ] **Step 1: Extract both, dict literals verbatim**

Key order inside the literals must not change — the report is serialised to
JSON and the gate compares bytes.

- [ ] **Step 2: Call them from the two loops.** The non-code branch becomes
      `file_reports.append(_non_code_file_report(file_data)); continue`, and
      the aggregate loop `file_report = _file_report_from_result(result)`.

- [ ] **Step 3: Verify** — contract, full suite, and `cmp` → `IDENTICAL`.

- [ ] **Step 4: Commit**

Message: `Extract the file-report builders out of review_repository`

---

### Task 6: Extract aggregation

**Files:**
- Modify: `backend/app/services/repository_review_engine.py`

**Interfaces:**
- Produces:
  ```python
  class _Aggregates(NamedTuple):
      file_reports: List[Dict]
      all_issues: List[Dict]
      prod_results: List[Dict]
      test_results: List[Dict]
      issue_files: int
      security_issues: int

  def _aggregate_results(results: List[Dict]) -> _Aggregates: ...
  ```
  `typing.NamedTuple` is stdlib — no new dependency. Returning six bare
  values in a tuple would be a positional trap for the next reader; the audit
  is about readability, so the return type is named.

- [ ] **Step 1: Move the whole `for result in results:` aggregate loop into
      `_aggregate_results`,** including the `file_path` normalisation and the
      `print(f"Processed file: {fpath}")` — that print is existing behaviour
      and removing it is a change, so it moves as-is.

- [ ] **Step 2: Call it**

```python
        agg = _aggregate_results(results)
        file_reports.extend(agg.file_reports)
        all_issues = agg.all_issues
        prod_results = agg.prod_results
        test_results = agg.test_results
        issue_files = agg.issue_files
        security_issues = agg.security_issues
```

`file_reports` already holds the non-code reports and the aggregate loop
appended to that same list, so **`extend` preserves ordering only if non-code
files came first**. They did not — the original loop interleaves. Therefore
`_aggregate_results` must NOT own ordering: keep `file_reports` as the
caller's list and pass it in as the first argument,
`_aggregate_results(results, file_reports)`, appending in place exactly as
before. Use that signature; drop `file_reports` from the NamedTuple.

- [ ] **Step 3: Verify** — contract, full suite, `cmp` → `IDENTICAL`.
      This task is the most likely to shift ordering; the gate is what catches it.

- [ ] **Step 4: Commit**

Message: `Extract result aggregation out of review_repository`

---

### Task 7: Extract scoring

**Files:**
- Modify: `backend/app/services/repository_review_engine.py`

**Interfaces:**
- Produces:
  ```python
  FILE_TYPE_WEIGHTS: Dict[str, float]      # module-level, was function-local

  class _Averages(NamedTuple):
      score: float
      documentation: float
      cyclomatic: float

  def _compute_averages(results, prod_results) -> _Averages: ...

  class _HealthScore(NamedTuple):
      quality: float
      security: int
      documentation: float
      simplicity: int
      composite: int

  def _compute_health_score(averages: _Averages, security_issues: int) -> _HealthScore: ...
  ```

- [ ] **Step 1: Lift `FILE_TYPE_WEIGHTS` to module level.** It is a documented
      policy constant (production 1.0, example 0.1, docs 0.05, test 0.0) and
      hiding it inside a branch is part of why this function was unreadable.

- [ ] **Step 2: Extract both helpers, arithmetic verbatim** — same `round()`
      calls, same precision, same `if prod_count > 0` guard returning zeros.
      Floating-point is not associative; do not "simplify" the two `sum()`
      comprehensions into one pass.

- [ ] **Step 3: Verify** — contract, full suite, `cmp` → `IDENTICAL`.
      `test_the_health_score_is_the_documented_weighted_composite` and the
      byte gate together pin this task.

- [ ] **Step 4: Commit**

Message: `Extract score averaging and the health composite`

---

### Task 8: Extract the six remaining report sections

**Files:**
- Modify: `backend/app/services/repository_review_engine.py`

**Interfaces:**
- Produces:
  - `_group_issues(all_issues) -> List[Dict]`
  - `_graph_centrality(dependency_graph, repo_data) -> Tuple[str, str]`
    (returns `(most_central_file, most_reused_module)`, both `"None"` when the
    graph is empty)
  - `_maintainability_warnings(prod_results) -> List[Dict]`
  - `_build_insights(grouped_issues, prod_results, most_central_file, most_reused_module) -> Dict`
  - `_attach_duplicates(file_reports, duplicates) -> None` (mutates)
  - `_architecture_summary(results) -> Tuple[Dict, Dict]`

- [ ] **Step 1: Extract all six, bodies verbatim.**

Two details that must survive untouched:
- `_graph_centrality` keeps the dead `in_degrees` accumulation. It is unused
  since B4 replaced the raw `max()` with `most_reused_first_party`, but
  deleting it is a **behaviour-neutral cleanup, not an extraction** — it goes
  in Task 9 with its own commit, so this task stays a pure move.
- `_architecture_summary` keeps both bare `except Exception:` fallbacks
  (`{}` and `{"god_objects": [], "layer_violations": []}`). They are the
  fail-soft contract; a repo that breaks the framework detector must still
  get a report.

- [ ] **Step 2: `review_repository` is now orchestration.** Read it top to
      bottom and confirm each line names a phase.

- [ ] **Step 3: Verify** — contract, full suite, `cmp` → `IDENTICAL`.

- [ ] **Step 4: Commit**

Message: `Extract issue grouping, centrality, warnings, insights and architecture`

---

### Task 9: Remove the dead accumulator, measure, and record

**Files:**
- Modify: `backend/app/services/repository_review_engine.py`
- Modify: `docs/HANDOVER.md`, `docs/DECISIONS.md`

- [ ] **Step 1: Delete the unused `in_degrees` accumulation** in
      `_graph_centrality`, keeping `out_degrees` which feeds
      `most_central_file`. Run the contract file and the gate; `IDENTICAL`
      proves it was dead.

- [ ] **Step 2: Measure the after-state**

```bash
venv/Scripts/python.exe scratchpad/cc.py
```
Record line count and CC for both entry points **and every extracted helper**.
Report the numbers measured, not the numbers hoped for — if a helper lands
above CC 15, say so rather than quietly accepting it.

- [ ] **Step 3: Run the full verification set**

```bash
venv/Scripts/python.exe -m pytest backend/tests -q
venv/Scripts/python.exe backend/benchmark/run_benchmark.py --gate
cd frontend && npm run typecheck && npx vitest run && npm run build
```
Expected: pytest ≥ 509 passed / 0 failed (500 existing + the new contract
file); **GATE PASSED** with no threshold lowered; frontend untouched and green.

- [ ] **Step 4: Self-scan.** Run this repository through the shipped analyzer
      and confirm both functions have dropped off the `complex_function`
      maintainability warnings — the tool grading its own decomposition.

- [ ] **Step 5: Update the docs.** `HANDOVER.md` §1b "What is genuinely left"
      loses its B1 row; add the measured before/after table. Append a
      `DECISIONS.md` entry recording the byte-identical gate as the method,
      and the `vulns` control-flow move in Task 3 as the one shape change.

- [ ] **Step 6: Commit**

Message: `Record B1 and the measured decomposition`

---

## Acceptance

| # | Criterion | How it is checked |
|---|---|---|
| 1 | Byte-identical report on a real 247-file repository | `cmp before.json after.json` |
| 2 | Backend suite green, count **increased** | `pytest backend/tests -q` → ≥ 509 passed, 0 failed |
| 3 | Detector gate unchanged | `run_benchmark.py --gate` → GATE PASSED, no threshold lowered |
| 4 | Both entry points substantially smaller | `cc.py` — from 385/CC 68 and 398/CC 58 |
| 5 | Every new test has been observed failing | perturbation steps in Tasks 1 and 4 |
| 6 | No new runtime dependency | `typing.NamedTuple` only; manifest unchanged |
| 7 | Frontend untouched and green | `tsc -b`, `vitest`, `npm run build` |

**Not claimed:** none of this is driven through the real UI. It is a pure
refactor gated on byte-identical output, which is a stronger guarantee than a
UI click-through would give — but it is not the same evidence, and §3 of the
handover sets the UI bar for feature work.
