# J3 Code Panes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the two code panes on the File Analysis page tell the truth — an
honest empty state and highlighted changed regions in the suggested file (F4),
and a prose account of what changed and why in place of the raw diff (F5).

**Architecture:** The two AST transforms in `HeuristicRefactorEngine` already
know exactly what they insert and where. They currently throw that away and the
summary re-derives it by counting `"""` characters, which is wrong. Both
transforms will return a structured change list alongside the code; that one
list becomes the source for the backend summary sentence, the frontend
highlighting, and the frontend prose. No new dependency, no LLM, no diffing in
the browser.

**Tech Stack:** Python 3.11 (`venv\Scripts\python.exe`), pytest, FastAPI ·
React 18 + TypeScript, Vite 5.4.21, vitest, Testing Library, Playwright,
Tailwind, shadcn/ui primitives.

**Spec:** `docs/superpowers/specs/2026-08-25-j3-code-panes-design.md` — read it
before Task 1. It records why the current summary is wrong and why the
`explanation` append is rebuilt rather than deleted.

## Global Constraints

- **No AI attribution in any commit message, PR body, tag or release.** No
  `Co-Authored-By`, no "Generated with". Pranav is the sole developer of record.
- **Never `git add -A` or `git add .`** — stage the explicit paths listed in each
  task. The tree carries a gitignored `.env` and stray zero-byte junk files.
- **Run `git status --short` after every commit.** Zero-byte junk files
  (`None\``, `1.0`, `bool`, `str`) appear from the toolchain. Delete what shows
  up with `rm -- '<name>'`; do not commit it.
- **The interpreter is `venv\Scripts\python.exe` at the repo root**, not
  `backend/venv`. Global Python 3.13 has no fastapi and dies at collection.
- **Typecheck with `npm run typecheck` (`tsc -b`), never `tsc --noEmit`.** The
  frontend tsconfig is solution-style (`"files": []` + `references`), so
  `--noEmit` compiles an empty program and exits 0 having checked nothing (D16).
- **Run all `npm` commands from `frontend/`**, never the repo root — the root
  resolves a different Vite major than the pinned 5.4.21. The Bash tool's
  working directory persists between calls, so use absolute paths.
- **No new runtime dependency.** The analysis layer is deliberately stdlib-only.
- **One logical change per commit.** Each task below is one commit.
- **Every new test must be watched failing first.** A test that passes both
  before and after the change measures nothing.
- Copy rule (CONSTRAINTS 18): nothing in this feature may describe the output as
  detected, reasoned about, or AI-generated. The transforms are mechanical and
  their output is unapplied.

**Baselines measured in session `e4ebf578` before any change** — do not inherit
these, but do compare against them:

| Command | Baseline |
|---|---|
| `venv\Scripts\python.exe -m pytest backend/tests -q` | `432 passed` in 122.67s |
| `npm test` from `frontend/` | `70 passed`, 11 files |

---

## File Structure

**Backend**

| File | Responsibility | Change |
|---|---|---|
| `backend/app/analysis/heuristic_refactor_engine.py` | The two AST transforms and the refactor result | Modify — transforms return `(code, changes)`; `generate_refactor` returns `"changes"`; the `"""`-counting block is replaced |
| `backend/app/services/repository_review_engine.py` | Assembles the per-file report | Modify — `final_output` gains `refactor_changes` |
| `backend/tests/test_heuristic_refactor.py` | Engine unit tests | Modify — add change-list tests |
| `backend/tests/test_repository_review.py` | Engine-to-report wiring | Modify — add one plumbing test |

**Frontend**

| File | Responsibility | Change |
|---|---|---|
| `frontend/src/lib/types.ts` | Shared types | Modify — add `RefactorChange`, `refactorChanges?` |
| `frontend/src/lib/response-mapper.ts` | Normalizes backend JSON at the boundary | Modify — add `normalizeRefactorChanges` |
| `frontend/src/components/CodeViewer.tsx` | Renders code with line numbers, patch colouring, changed-line marking | **Create** — extracted from `FileAnalysis.tsx` so two panes can share it |
| `frontend/src/components/SuggestedEditsPane.tsx` | F4 — empty state or highlighted improved file | **Create** |
| `frontend/src/components/WhatChangedPane.tsx` | F5 — prose, raw-diff disclosure, pre-J3 fallback | **Create** |
| `frontend/src/pages/FileAnalysis.tsx` | The page; owns the tab strip | Modify — imports the three components above, inline `CodeViewer` removed |
| `frontend/src/pages/FileAnalysis.test.tsx` | Page-level tests | **Create** — the page has no test file today |
| `frontend/src/lib/mock-data.ts` | Demo fixture | Modify — one file with changes, one without |
| `frontend/e2e/findings.spec.ts` | Playwright | Modify — one assertion over the demo |

`FileAnalysis.tsx` is ~300 lines and already holds the page shell, the sidebar,
the filters and the code viewer. Pulling the viewer and the two panes into their
own files is the split that lets each be tested directly; it is not unrelated
refactoring.

`EmptyState` is deliberately **not** reused for the F4 empty state: it is a
full-page placeholder (`h-[60vh]`, centred) meant for "no scan yet", and it
would dwarf a pane inside a card.

---

### Task 1: The change list — backend transforms

**Files:**
- Modify: `backend/app/analysis/heuristic_refactor_engine.py:49-143` (docstring pass), `:145-188` (hint pass), `:262-281` (the summary block), `:285-295` (the return dict)
- Test: `backend/tests/test_heuristic_refactor.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `HeuristicRefactorEngine.generate_refactor(...)` returns a dict that
  now also carries `"changes": List[Dict[str, Any]]`. Each record is exactly:
  `{"kind": "docstring" | "return_hint", "target": "function" | "class",
  "name": str, "line": int, "line_count": int}`. `line` is **1-based, in the
  improved file**. `_add_missing_docstrings(code)` and
  `_add_type_hints_to_simple_functions(code)` both return
  `Tuple[str, List[Dict[str, Any]]]` instead of `str`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_heuristic_refactor.py`:

```python
# ---------------------------------------------------------
# J3 (F5): the structured change list
#
# The old summary counted lines containing `"""` and divided by two, which
# assumes every docstring spans two such lines. The engine emits a SINGLE-line
# docstring for classes and for parameterless functions, so that arithmetic
# reported zero for exactly the files it had just changed. These tests assert
# the change list, and assert each line number against the improved TEXT --
# a count assertion cannot see an off-by-one, this can.
# ---------------------------------------------------------

EMPTY_ANALYSIS = {"analysis": {"explanation": "", "suggestions": []}}


def _refactor(code):
    """Run the engine over `code` with no complexity or smell input."""
    engine = HeuristicRefactorEngine()
    return engine.generate_refactor(code, EMPTY_ANALYSIS, {}, {})


def test_changes_are_returned_for_a_parameterless_function():
    result = _refactor('def hello():\n    print("hello world")\n')

    changes = result["changes"]
    docstrings = [c for c in changes if c["kind"] == "docstring"]
    hints = [c for c in changes if c["kind"] == "return_hint"]

    assert len(docstrings) == 1
    assert docstrings[0]["target"] == "function"
    assert docstrings[0]["name"] == "hello"
    assert docstrings[0]["line_count"] == 1

    assert len(hints) == 1
    assert hints[0]["name"] == "hello"


def test_change_line_numbers_point_at_the_improved_text():
    result = _refactor('def hello():\n    print("hello world")\n')

    improved = result["improved_code"].splitlines()

    for change in result["changes"]:
        line = improved[change["line"] - 1]
        if change["kind"] == "docstring":
            assert '"""' in line
        else:
            assert "-> None" in line


def test_multi_line_docstring_spans_the_lines_it_claims():
    code = "def add(a, b):\n    total = a + b\n    return total\n"

    result = _refactor(code)

    docstrings = [c for c in result["changes"] if c["kind"] == "docstring"]
    assert len(docstrings) == 1
    change = docstrings[0]

    improved = result["improved_code"].splitlines()
    block = improved[change["line"] - 1 : change["line"] - 1 + change["line_count"]]

    # The claimed span must open and close the docstring and contain nothing else.
    assert '"""' in block[0]
    assert '"""' in block[-1]
    assert "total = a + b" not in "\n".join(block)


def test_class_docstrings_are_reported_as_classes():
    result = _refactor("class Widget:\n    size = 1\n")

    docstrings = [c for c in result["changes"] if c["kind"] == "docstring"]
    assert len(docstrings) == 1
    assert docstrings[0]["target"] == "class"
    assert docstrings[0]["name"] == "Widget"


def test_line_numbers_survive_several_insertions_above():
    code = (
        "def first():\n    pass\n\n"
        "def second():\n    pass\n\n"
        "def third():\n    pass\n"
    )

    result = _refactor(code)
    improved = result["improved_code"].splitlines()

    docstrings = [c for c in result["changes"] if c["kind"] == "docstring"]
    assert len(docstrings) == 3

    # Every docstring's line must still land on a docstring after the two
    # insertions above it have shifted the file down.
    for change in docstrings:
        assert '"""' in improved[change["line"] - 1]


def test_a_file_with_no_gaps_reports_no_changes():
    code = 'def done() -> None:\n    """Already documented."""\n    print("x")\n'

    result = _refactor(code)

    assert result["changes"] == []


def test_summary_counts_single_line_docstrings_correctly():
    """The `// 2` bug: one parameterless function reported 'to 0'."""
    result = _refactor('def hello():\n    print("hello world")\n')

    explanation = result["explanation"]

    assert "Suggested improvements (unapplied)" in explanation
    assert "to 0 " not in explanation
    assert "1 function" in explanation
```

- [ ] **Step 2: Run them to verify they fail**

```
D:\ETPROJECT\venv\Scripts\python.exe -m pytest backend/tests/test_heuristic_refactor.py -q
```

Expected: the six `changes`-based tests fail with `KeyError: 'changes'`, and
`test_summary_counts_single_line_docstrings_correctly` fails on the
`"to 0 " not in explanation` assertion — that failure is the bug the spec
describes, observed rather than argued. **Record the exact failure output; a
test that does not fail here is not testing anything.**

- [ ] **Step 3: Make the docstring pass return its change list**

Change the signature at `:49`:

```python
    def _add_missing_docstrings(self, code: str) -> Tuple[str, List[Dict[str, Any]]]:
```

and add `Tuple` to the typing import at the top of the file:

```python
from typing import Dict, Any, List, Tuple
```

Both early returns must return a pair — the `except SyntaxError` return and the
`if not insertions` return:

```python
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code, []
```

```python
        if not insertions:
            return code, []
```

Replace the reverse-order insertion block at the end of the method (currently
`insertions.sort(key=lambda x: x[0], reverse=True)` through `return "".join(lines)`)
with this. The docstring text itself is unchanged — only the ordering, the
bookkeeping and the return differ:

```python
        # Insert ASCENDING and carry two counters. `elements_added` tracks list
        # positions (each insertion adds one element, however many lines it
        # holds); `lines_added` tracks rendered lines, which is what a line
        # number in the improved file means. Conflating them puts a multi-line
        # docstring's own body into the next change's line number.
        insertions.sort(key=lambda x: x[0])

        changes: List[Dict[str, Any]] = []
        elements_added = 0
        lines_added = 0

        for line_num, indent, name, kind, params in insertions:
            indent_str = " " * indent

            if kind == "class":
                docstring = f'{indent_str}"""Class {name}."""\n'
            elif params:
                param_docs = "\n".join(f"{indent_str}    {p}: Description." for p in params)
                docstring = (
                    f'{indent_str}"""\n'
                    f'{indent_str}{name.replace("_", " ").capitalize()}.\n'
                    f'\n'
                    f'{indent_str}Args:\n'
                    f'{param_docs}\n'
                    f'{indent_str}"""\n'
                )
            else:
                docstring = f'{indent_str}"""{name.replace("_", " ").capitalize()}."""\n'

            lines.insert(line_num + elements_added, docstring)

            line_count = docstring.count("\n")

            changes.append({
                "kind": "docstring",
                "target": "class" if kind == "class" else "function",
                "name": name,
                "line": line_num + lines_added + 1,
                "line_count": line_count,
            })

            elements_added += 1
            lines_added += line_count

        return "".join(lines), changes
```

- [ ] **Step 4: Make the hint pass return its change list**

At `:145`, change the signature and capture the function name in the
modification tuple:

```python
    def _add_type_hints_to_simple_functions(self, code: str) -> Tuple[str, List[Dict[str, Any]]]:
```

The `except SyntaxError` early return becomes `return code, []`.

Where the modification is recorded, add the name:

```python
                        if "):" in line and "-> " not in line:
                            modifications.append((def_line, node.name, "):", ") -> None:"))
```

And the application block at the end becomes:

```python
        # This pass re-parses the already-docstringed code, so `def_line` is
        # already an improved-file coordinate, and replacing in place changes
        # no line count -- these records need no offset and do not invalidate
        # the docstring records computed before them.
        modifications.sort(key=lambda x: x[0], reverse=True)

        changes: List[Dict[str, Any]] = []

        for line_num, name, old, new in modifications:
            lines[line_num] = lines[line_num].replace(old, new, 1)
            changes.append({
                "kind": "return_hint",
                "target": "function",
                "name": name,
                "line": line_num + 1,
                "line_count": 1,
            })

        changes.sort(key=lambda c: c["line"])

        return "\n".join(lines), changes
```

- [ ] **Step 5: Wire both into `generate_refactor`**

At `:216-224`, the two calls become:

```python
        # Add docstrings to undocumented functions
        improved_code, docstring_changes = self._add_missing_docstrings(improved_code)

        # Add type hints to simple functions
        improved_code, hint_changes = self._add_type_hints_to_simple_functions(improved_code)

        changes = docstring_changes + hint_changes
```

- [ ] **Step 6: Replace the `"""`-counting summary**

Delete the whole block from `if improved_code != code:` down to the
`explanation = f"{explanation}\n\n**Suggested improvements (unapplied):** ..."`
line (currently `:264-281`) and put this in its place:

```python
        # The summary is built from the change list, not by counting `"""`
        # lines. The old arithmetic divided that count by two, which assumed
        # every docstring spanned two lines -- but classes and parameterless
        # functions get a single-line docstring, so a file whose only gaps were
        # those reported "to 0" while the pane beside it showed the insertions.
        if changes:
            doc_functions = sum(
                1 for c in changes if c["kind"] == "docstring" and c["target"] == "function"
            )
            doc_classes = sum(
                1 for c in changes if c["kind"] == "docstring" and c["target"] == "class"
            )
            hint_count = sum(1 for c in changes if c["kind"] == "return_hint")

            parts = []

            if doc_functions or doc_classes:
                targets = []
                if doc_functions:
                    targets.append(f"{doc_functions} function" + ("" if doc_functions == 1 else "s"))
                if doc_classes:
                    targets.append(f"{doc_classes} class" + ("" if doc_classes == 1 else "es"))
                parts.append("Added placeholder docstrings to " + " and ".join(targets))

            if hint_count:
                parts.append(
                    f"Added `-> None` return hints to {hint_count} function"
                    + ("" if hint_count == 1 else "s")
                )

            improvement_desc = ". ".join(parts) + "."
            explanation = f"{explanation}\n\n**Suggested improvements (unapplied):** {improvement_desc}"
```

- [ ] **Step 7: Return the change list**

The final return of `generate_refactor` (`:288-295`) gains one key:

```python
        return {
            "explanation": explanation,
            "suggestions": suggestions,
            "improved_code": improved_code,
            "patch": patch,
            "changes": changes
        }
```

- [ ] **Step 8: Run the new tests, then the whole backend suite**

```
D:\ETPROJECT\venv\Scripts\python.exe -m pytest backend/tests/test_heuristic_refactor.py -q
D:\ETPROJECT\venv\Scripts\python.exe -m pytest backend/tests -q
```

Expected: the file passes, and the full suite reports **at least 432 passed, 0
failed** (baseline 432 + the 7 added here = 439). Read the count, not just the
exit code.

- [ ] **Step 9: Commit**

```bash
git add backend/app/analysis/heuristic_refactor_engine.py backend/tests/test_heuristic_refactor.py
git commit -F <commit-message-file>
```

Message, in the repo's voice — what changed and why, no attribution:

```
Have the refactor transforms report what they changed

Both AST passes knew exactly what they inserted and threw it away, so the
summary re-derived it by counting lines containing `"""` and dividing by two.
That assumes every docstring spans two such lines; the engine emits a
single-line docstring for classes and parameterless functions, so a file whose
only gaps were those reported "Added docstrings to 0" while the improved pane
showed the insertions it had just made.

Each pass now returns a change record per edit, carrying the symbol name and
its 1-based line in the improved file, and the summary is counted from that
list. The docstring pass inserts ascending and tracks list positions separately
from rendered lines, because a multi-line docstring adds one element but
several lines and conflating the two puts a docstring's own body into the next
change's line number.
```

Then `git status --short` and delete any zero-byte junk that appears.

---

### Task 2: Carry the change list into the file report

**Files:**
- Modify: `backend/app/services/repository_review_engine.py:136-141` (the failure fallback), `:250-260` (`final_output`)
- Test: `backend/tests/test_repository_review.py`

**Interfaces:**
- Consumes: `generate_refactor(...)["changes"]` from Task 1.
- Produces: each per-file report dict carries `"refactor_changes": List[Dict]`,
  the same records Task 1 defined. Consumed by Task 3's mapper as
  `f.refactor_changes`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_repository_review.py`:

```python
# ---------------------------------------------------------
# J3: the change list has to survive the trip to the report
#
# The engine producing `changes` is worthless if the report drops them --
# this is the seam the frontend actually reads.
# ---------------------------------------------------------

@patch(_PATCH_TARGET, return_value=MOCK_ANALYSIS)
def test_file_report_carries_the_refactor_change_list(mock_llm):
    with tempfile.TemporaryDirectory() as repo:
        with open(os.path.join(repo, "example.py"), "w") as f:
            f.write('def hello():\n    print("hello world")\n')

        engine = RepositoryReviewEngine()
        repo_data = analyze_repository(repo)
        result = engine.review_repository(repo, repo_data)

        report = result["file_reports"][0]

        assert "refactor_changes" in report

        kinds = {c["kind"] for c in report["refactor_changes"]}
        assert kinds == {"docstring", "return_hint"}

        for change in report["refactor_changes"]:
            assert change["line"] >= 1
            assert change["name"] == "hello"
```

- [ ] **Step 2: Run it to verify it fails**

```
D:\ETPROJECT\venv\Scripts\python.exe -m pytest backend/tests/test_repository_review.py::test_file_report_carries_the_refactor_change_list -q
```

Expected: FAIL on `assert "refactor_changes" in report`.

- [ ] **Step 3: Add the key to `final_output`**

In `analyze_single_file`, alongside the existing `"patch"` entry:

```python
        "patch": refactor_result.get("patch", None),
        # J3 (F4/F5): the structured edits behind `refactor_suggestion`, so the
        # UI can highlight exactly what changed and say so in prose instead of
        # re-deriving it from a rendered diff.
        "refactor_changes": refactor_result.get("changes", []),
```

- [ ] **Step 4: Add it to the analysis-failure fallback too**

The `except Exception` branch builds a stand-in `refactor_result`. Without the
key there, a file that fails analysis reaches `.get("changes", [])` — which is
safe, but leaving the shapes different invites a future reader to assume the
fallback matches the real thing. Make them match:

```python
        refactor_result = {
            "improved_code": "",
            "explanation": "",
            "suggestions": [],
            "patch": None,
            "changes": []
        }
```

- [ ] **Step 5: Run the test, then the whole backend suite**

```
D:\ETPROJECT\venv\Scripts\python.exe -m pytest backend/tests/test_repository_review.py -q
D:\ETPROJECT\venv\Scripts\python.exe -m pytest backend/tests -q
```

Expected: PASS; full suite ≥ 440 passed, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/repository_review_engine.py backend/tests/test_repository_review.py
git commit -F <commit-message-file>
```

```
Carry the refactor change list into the file report

The transforms report their edits now, but the per-file report dropped them, so
the only thing reaching the UI was still the rendered diff. Adds
`refactor_changes` beside `patch`, and gives the analysis-failure fallback the
same shape so the two cannot drift.
```

Then `git status --short` and delete any junk.

---

### Task 3: Types and the boundary normalizer

**Files:**
- Modify: `frontend/src/lib/types.ts:60-62` area, `frontend/src/lib/response-mapper.ts:238-241` area
- Test: `frontend/src/lib/response-mapper.test.ts`

**Interfaces:**
- Consumes: `refactor_changes` from Task 2.
- Produces: `RefactorChange` (exported from `@/lib/types`) with fields
  `kind: "docstring" | "return_hint"`, `target: "function" | "class"`,
  `name: string`, `line: number`, `lineCount: number`. `FileRecord` gains
  `refactorChanges?: RefactorChange[]`. Tasks 4-6 import `RefactorChange` from
  `@/lib/types` and read `file.refactorChanges`.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/lib/response-mapper.test.ts`. The entry point is
`mapApiResponse(data, repoUrl)`, the backend's file list arrives under
`file_reports`, and the file already defines `const REPO` at the top — reuse
it, and do not re-import `mapApiResponse`, it is already imported there:

```ts
describe("mapApiResponse — refactor changes", () => {
  it("maps the backend's snake_case change records", () => {
    const report = mapApiResponse(
      {
        file_reports: [
          {
            file_path: "src/main.py",
            refactor_changes: [
              { kind: "docstring", target: "function", name: "hello", line: 2, line_count: 1 },
              { kind: "return_hint", target: "function", name: "hello", line: 1, line_count: 1 },
            ],
          },
        ],
      },
      REPO
    );

    expect(report.files[0].refactorChanges).toEqual([
      { kind: "docstring", target: "function", name: "hello", line: 2, lineCount: 1 },
      { kind: "return_hint", target: "function", name: "hello", line: 1, lineCount: 1 },
    ]);
  });

  it("drops malformed records at the boundary rather than rendering them", () => {
    const report = mapApiResponse(
      {
        file_reports: [
          {
            file_path: "src/main.py",
            refactor_changes: [
              { kind: "wat", target: "function", name: "x", line: 1, line_count: 1 },
              { kind: "docstring", target: "module", name: "x", line: 1, line_count: 1 },
              { kind: "docstring", target: "function", name: "x", line: 0, line_count: 1 },
              { kind: "docstring", target: "function", name: "ok", line: 3, line_count: 2 },
            ],
          },
        ],
      },
      REPO
    );

    expect(report.files[0].refactorChanges).toEqual([
      { kind: "docstring", target: "function", name: "ok", line: 3, lineCount: 2 },
    ]);
  });

  it("gives a scan recorded before change tracking an empty list, not undefined", () => {
    const report = mapApiResponse(
      { file_reports: [{ file_path: "src/main.py", patch: "--- a/x" }] },
      REPO
    );

    expect(report.files[0].refactorChanges).toEqual([]);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```
cd D:\ETPROJECT\frontend
npx vitest run src/lib/response-mapper.test.ts
```

Expected: FAIL — `refactorChanges` is `undefined`.

- [ ] **Step 3: Add the type**

In `frontend/src/lib/types.ts`, above the file-record interface:

```ts
/**
 * One mechanical edit the heuristic refactor engine suggests.
 *
 * `line` is 1-based **in the improved file**, and `lineCount` is how many of
 * its lines the edit occupies — a parameterised docstring spans several. The
 * engine reports these directly; nothing here is derived from a diff.
 */
export interface RefactorChange {
  kind: "docstring" | "return_hint";
  target: "function" | "class";
  name: string;
  line: number;
  lineCount: number;
}
```

and inside the file-record interface, beside `patch`:

```ts
  patch: string | null;
  /** Empty for scans recorded before J3 added change tracking. */
  refactorChanges?: RefactorChange[];
```

- [ ] **Step 4: Add the normalizer**

In `frontend/src/lib/response-mapper.ts`, next to `normalizeVulnerabilities`:

```ts
/**
 * Coerce the backend's change records into `RefactorChange` objects.
 *
 * Follows the precedent `normalizeVulnerabilities` set: a bad shape is
 * neutralised where it enters, so no consumer has to guard. Scans persisted
 * before J3 carry no `refactor_changes` at all and normalize to `[]`, which is
 * what the panes read as "this scan predates change tracking".
 */
function normalizeRefactorChanges(raw: any): RefactorChange[] {
  if (!Array.isArray(raw)) return [];

  const changes: RefactorChange[] = [];

  for (const c of raw) {
    if (!c || typeof c !== "object") continue;

    const { kind, target } = c;
    if (kind !== "docstring" && kind !== "return_hint") continue;
    if (target !== "function" && target !== "class") continue;

    const line = Number(c.line);
    if (!Number.isFinite(line) || line < 1) continue;

    const rawCount = Number(c.line_count ?? c.lineCount ?? 1);
    const lineCount = Number.isFinite(rawCount) && rawCount >= 1 ? rawCount : 1;

    changes.push({
      kind,
      target,
      name: typeof c.name === "string" ? c.name : "",
      line,
      lineCount,
    });
  }

  return changes;
}
```

Import `RefactorChange` in that file's type import, and add to the returned
record beside `patch`:

```ts
    patch: f.patch || f.diff || null,
    refactorChanges: normalizeRefactorChanges(f.refactor_changes),
```

- [ ] **Step 5: Run the tests and the typecheck**

```
cd D:\ETPROJECT\frontend
npx vitest run src/lib/response-mapper.test.ts
npm run typecheck
```

Expected: PASS, and typecheck exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/response-mapper.ts frontend/src/lib/response-mapper.test.ts
git commit -F <commit-message-file>
```

```
Normalize the refactor change list at the boundary

The change records reach the frontend as loose JSON, and history replays scans
persisted long before this field existed. Both cases are handled where the data
enters, the way vulnerability records already are: an unknown kind or a line
number below 1 is dropped rather than guarded at every consumer, and a scan
with no records normalizes to an empty list instead of undefined.
```

---

### Task 4: `CodeViewer` moves out and learns to mark changed lines

**Files:**
- Create: `frontend/src/components/CodeViewer.tsx`
- Create: `frontend/src/components/CodeViewer.test.tsx`
- Modify: `frontend/src/pages/FileAnalysis.tsx:20-61` (delete the inline copy), and its three call sites at `:288`, `:291`, `:295`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `export function CodeViewer({ code, isPatch, highlightedLines })`
  from `@/components/CodeViewer`, where `highlightedLines?: ReadonlySet<number>`
  holds 1-based line numbers. Tasks 5 and 6 import it.

This is an additive checkpoint (CONSTRAINTS 16): the new file is created and
green before the inline copy is deleted, so the tree never goes red.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/CodeViewer.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CodeViewer } from "./CodeViewer";

const CODE = ["def hello():", '    """Hello."""', '    print("x")'].join("\n");

describe("CodeViewer", () => {
  it("numbers every line from 1", () => {
    render(<CodeViewer code={CODE} />);

    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("marks exactly the lines it is given, and no others", () => {
    const { container } = render(
      <CodeViewer code={CODE} highlightedLines={new Set([2])} />
    );

    const marked = container.querySelectorAll('[data-changed="true"]');

    expect(marked).toHaveLength(1);
    expect(marked[0].textContent).toContain('"""Hello."""');
  });

  it("does not rely on colour alone to say a line changed", () => {
    render(<CodeViewer code={CODE} highlightedLines={new Set([2])} />);

    // One announced marker per changed line, for anyone not seeing the tint.
    expect(screen.getAllByText("Changed line.")).toHaveLength(1);
  });

  it("colours a unified diff by its leading character", () => {
    const { container } = render(
      <CodeViewer code={"@@ -1 +1 @@\n-old\n+new"} isPatch />
    );

    expect(container.textContent).toContain("+new");
    expect(container.querySelectorAll('[data-changed="true"]')).toHaveLength(0);
  });

  it("says so when there is nothing to show", () => {
    render(<CodeViewer code="" />);

    expect(screen.getByText("Not available")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```
cd D:\ETPROJECT\frontend
npx vitest run src/components/CodeViewer.test.tsx
```

Expected: FAIL — the module does not exist.

- [ ] **Step 3: Create the component**

`frontend/src/components/CodeViewer.tsx`. The patch-colouring branch is the
existing behaviour moved verbatim; the changed-line branch is new:

```tsx
import { cn } from "@/lib/utils";

interface CodeViewerProps {
  code: string;
  /** Colour the content as a unified diff rather than as source. */
  isPatch?: boolean;
  /**
   * 1-based line numbers to mark as changed. Ignored when `isPatch` is set —
   * a diff already carries its own +/- signal and stacking a second one on top
   * would say the same thing twice.
   */
  highlightedLines?: ReadonlySet<number>;
}

/**
 * Renders code with line numbers, in one of three modes: plain source, a
 * unified diff coloured by leading character, or source with specific lines
 * marked as changed.
 *
 * Lived inline in FileAnalysis until J3, when a second pane needed it.
 */
export function CodeViewer({ code, isPatch = false, highlightedLines }: CodeViewerProps) {
  if (!code) return <span>Not available</span>;

  const lines = code.split("\n");
  const marking = !isPatch && highlightedLines !== undefined;

  return (
    <div className="flex flex-col font-mono text-[13px] leading-snug w-full min-w-max">
      {lines.map((line, i) => {
        const lineNumber = i + 1;
        const isChanged = marking && highlightedLines.has(lineNumber);

        let bgColor = "transparent";
        let textColor = "text-foreground/80";

        if (isPatch) {
          if (line.startsWith("+") && !line.startsWith("+++")) {
            bgColor = "bg-primary/20";
            textColor = "text-primary border-l-2 border-primary";
          } else if (line.startsWith("-") && !line.startsWith("---")) {
            bgColor = "bg-destructive/20";
            textColor = "text-destructive border-l-2 border-destructive";
          } else if (line.startsWith("@@")) {
            textColor = "text-info font-bold";
            bgColor = "bg-info/10";
          } else {
            textColor = "text-muted-foreground";
          }
        } else if (isChanged) {
          bgColor = "bg-primary/15";
          textColor = "text-foreground";
        }

        return (
          <div
            key={i}
            data-changed={isChanged ? "true" : undefined}
            className={cn("flex px-2 hover:bg-white/5", bgColor, isChanged && "border-l-2 border-primary")}
          >
            {marking && (
              <span aria-hidden="true" className="w-3 shrink-0 select-none text-primary">
                {isChanged ? "+" : " "}
              </span>
            )}
            <span className="w-10 shrink-0 text-muted-foreground/50 select-none text-right pr-4 border-r border-border/50 mr-4">
              {lineNumber}
            </span>
            {isChanged && <span className="sr-only">Changed line. </span>}
            <span className={`whitespace-pre ${textColor}`}>{line || " "}</span>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

```
cd D:\ETPROJECT\frontend
npx vitest run src/components/CodeViewer.test.tsx
```

Expected: 5 passed.

- [ ] **Step 5: Switch `FileAnalysis.tsx` to the shared component**

Delete the inline `CodeViewer` const and its `// Helper to render code...`
comment (`:20-61`), and add to the imports:

```tsx
import { CodeViewer } from "@/components/CodeViewer";
```

The three call sites keep their existing props and need no other change.

- [ ] **Step 6: Verify nothing regressed**

```
cd D:\ETPROJECT\frontend
npm test
npm run typecheck
```

Expected: all previously passing tests still pass (baseline 70 + this task's 5 +
Task 3's 3 = 78), typecheck exit 0.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/CodeViewer.tsx frontend/src/components/CodeViewer.test.tsx frontend/src/pages/FileAnalysis.tsx
git commit -F <commit-message-file>
```

```
Lift CodeViewer out of the page so two panes can share it

The viewer was a const inside FileAnalysis, which is fine for one caller and
untestable on its own. It moves to its own component with the patch-colouring
behaviour unchanged, and gains a third mode: mark a given set of 1-based lines
as changed. The marker is a gutter character and an announced label as well as
a tint, so it survives being read without colour.
```

---

### Task 5: F4 — the "Suggested edits" pane

**Files:**
- Create: `frontend/src/components/SuggestedEditsPane.tsx`
- Create: `frontend/src/components/SuggestedEditsPane.test.tsx`
- Modify: `frontend/src/pages/FileAnalysis.tsx` (the tab strip and the improved tab body)

**Interfaces:**
- Consumes: `CodeViewer` (Task 4), `RefactorChange` (Task 3).
- Produces: `export function SuggestedEditsPane({ improvedCode, originalCode, changes })`
  where `changes: RefactorChange[]`. Rendered by `FileAnalysis` under the tab
  labelled **"Suggested edits"** (tab value `"suggested"`).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/SuggestedEditsPane.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SuggestedEditsPane } from "./SuggestedEditsPane";
import type { RefactorChange } from "@/lib/types";

const ORIGINAL = 'def hello():\n    print("x")';
const IMPROVED = 'def hello() -> None:\n    """Hello."""\n    print("x")';

const CHANGES: RefactorChange[] = [
  { kind: "return_hint", target: "function", name: "hello", line: 1, lineCount: 1 },
  { kind: "docstring", target: "function", name: "hello", line: 2, lineCount: 1 },
];

describe("SuggestedEditsPane", () => {
  it("names what was checked instead of implying a clean bill of health", () => {
    render(<SuggestedEditsPane improvedCode={ORIGINAL} originalCode={ORIGINAL} changes={[]} />);

    expect(screen.getByText(/Nothing to suggest here/i)).toBeInTheDocument();
    expect(screen.getByText(/no docstring/i)).toBeInTheDocument();
    expect(screen.getByText(/not a clean bill of health/i)).toBeInTheDocument();
  });

  it("treats an empty improved file as nothing to suggest", () => {
    render(<SuggestedEditsPane improvedCode="" originalCode={ORIGINAL} changes={[]} />);

    expect(screen.getByText(/Nothing to suggest here/i)).toBeInTheDocument();
  });

  it("shows the full improved file, not just the changed parts", () => {
    const { container } = render(
      <SuggestedEditsPane improvedCode={IMPROVED} originalCode={ORIGINAL} changes={CHANGES} />
    );

    expect(container.textContent).toContain('print("x")');
  });

  it("highlights every line a change claims and nothing else", () => {
    const { container } = render(
      <SuggestedEditsPane improvedCode={IMPROVED} originalCode={ORIGINAL} changes={CHANGES} />
    );

    const marked = Array.from(container.querySelectorAll('[data-changed="true"]'));

    expect(marked).toHaveLength(2);
    expect(marked[0].textContent).toContain("-> None");
    expect(marked[1].textContent).toContain('"""Hello."""');
  });

  it("spans every line of a multi-line change", () => {
    const improved = ["def add(a, b):", '    """', "    Add.", '    """', "    return a + b"].join("\n");
    const changes: RefactorChange[] = [
      { kind: "docstring", target: "function", name: "add", line: 2, lineCount: 3 },
    ];

    const { container } = render(
      <SuggestedEditsPane improvedCode={improved} originalCode="def add(a, b):" changes={changes} />
    );

    expect(container.querySelectorAll('[data-changed="true"]')).toHaveLength(3);
  });

  it("counts the highlighted lines for the reader", () => {
    render(<SuggestedEditsPane improvedCode={IMPROVED} originalCode={ORIGINAL} changes={CHANGES} />);

    expect(screen.getByText(/2 changed lines highlighted/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```
cd D:\ETPROJECT\frontend
npx vitest run src/components/SuggestedEditsPane.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 3: Create the component**

`frontend/src/components/SuggestedEditsPane.tsx`:

```tsx
import { useMemo } from "react";
import { CodeViewer } from "@/components/CodeViewer";
import type { RefactorChange } from "@/lib/types";

interface SuggestedEditsPaneProps {
  improvedCode: string;
  originalCode: string;
  changes: RefactorChange[];
}

/**
 * F4. The pane was labelled "Improved" and, when the engine had nothing to
 * add, rendered the file unchanged with no explanation — which reads as a
 * clean bill of health for a file that had two narrow checks run against it.
 *
 * The engine applies exactly two transforms, so the empty state names both and
 * says what was NOT attempted. Nothing here is applied to the repository.
 */
export function SuggestedEditsPane({ improvedCode, originalCode, changes }: SuggestedEditsPaneProps) {
  const highlightedLines = useMemo(() => {
    const lines = new Set<number>();
    for (const change of changes) {
      for (let n = change.line; n < change.line + Math.max(1, change.lineCount); n++) {
        lines.add(n);
      }
    }
    return lines;
  }, [changes]);

  const hasEdits = changes.length > 0 && !!improvedCode && improvedCode !== originalCode;

  if (!hasEdits) {
    return (
      <div role="status" className="rounded-lg border border-border/50 bg-background p-6 text-sm">
        <p className="font-medium text-foreground">Nothing to suggest here.</p>
        <p className="mt-2 text-muted-foreground">
          Two checks ran against this file: functions and classes with no docstring, and
          functions that never return a value but have no <code>&rarr; None</code> hint.
          This file has neither gap.
        </p>
        <p className="mt-2 text-muted-foreground">
          No other transform was attempted — this is not a clean bill of health.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        {highlightedLines.size} changed {highlightedLines.size === 1 ? "line" : "lines"} highlighted.
        These edits are suggestions and have not been applied to the repository.
      </p>
      <div className="bg-background border border-border/50 rounded-lg overflow-x-auto overflow-y-auto max-h-[600px] py-4 shadow-inner">
        <CodeViewer code={improvedCode} highlightedLines={highlightedLines} />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

```
cd D:\ETPROJECT\frontend
npx vitest run src/components/SuggestedEditsPane.test.tsx
```

Expected: 6 passed.

- [ ] **Step 5: Wire it into the page and rename the tab**

In `frontend/src/pages/FileAnalysis.tsx`, add the import:

```tsx
import { SuggestedEditsPane } from "@/components/SuggestedEditsPane";
```

Replace the improved trigger and its content:

```tsx
                    <TabsTrigger value="suggested">Suggested edits</TabsTrigger>
```

```tsx
                  <TabsContent value="suggested" className="min-w-0">
                    <SuggestedEditsPane
                      improvedCode={file.improved_code}
                      originalCode={file.original_code}
                      changes={file.refactorChanges ?? []}
                    />
                  </TabsContent>
```

The old `<TabsContent value="improved">` wrapper div is removed — the pane owns
its own container now.

- [ ] **Step 6: Verify**

```
cd D:\ETPROJECT\frontend
npm test
npm run typecheck
```

Expected: 84 passed (78 + 6), typecheck exit 0.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/SuggestedEditsPane.tsx frontend/src/components/SuggestedEditsPane.test.tsx frontend/src/pages/FileAnalysis.tsx
git commit -F <commit-message-file>
```

```
Say what was checked in the suggested-edits pane, and mark what changed

The pane was called "Improved" and, with nothing to add, rendered the file
unchanged and silent. Both overstate what happened: the engine inserts
placeholder docstrings and `-> None` hints and does nothing else, so an
unchanged file means those two checks found no gap, not that the file is fine.
The empty state now names both checks and says no other transform ran.

When there are edits, the full file renders with the engine's own line numbers
highlighted, so a reader can see which regions the suggestion touches without
reading a diff.
```

---

### Task 6: F5 — the "What changed" pane

**Files:**
- Create: `frontend/src/components/WhatChangedPane.tsx`
- Create: `frontend/src/components/WhatChangedPane.test.tsx`
- Modify: `frontend/src/pages/FileAnalysis.tsx` (the patch trigger and content)

**Interfaces:**
- Consumes: `CodeViewer` (Task 4), `RefactorChange` (Task 3), and the
  `Collapsible` / `CollapsibleTrigger` / `CollapsibleContent` primitives from
  `@/components/ui/collapsible` (the same set `FindingCard` uses).
- Produces: `export function WhatChangedPane({ changes, patch })` where
  `patch: string | null`. Rendered under the tab labelled **"What changed"**
  (tab value `"changed"`), which appears when
  `(file.refactorChanges?.length ?? 0) > 0 || !!file.patch`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/WhatChangedPane.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WhatChangedPane } from "./WhatChangedPane";
import type { RefactorChange } from "@/lib/types";

const PATCH = "--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@\n-def hello():\n+def hello() -> None:";

const CHANGES: RefactorChange[] = [
  { kind: "docstring", target: "function", name: "hello", line: 2, lineCount: 1 },
  { kind: "docstring", target: "function", name: "world", line: 6, lineCount: 1 },
  { kind: "docstring", target: "class", name: "Widget", line: 12, lineCount: 1 },
  { kind: "return_hint", target: "function", name: "hello", line: 1, lineCount: 1 },
];

describe("WhatChangedPane", () => {
  it("counts each kind of edit in prose", () => {
    render(<WhatChangedPane changes={CHANGES} patch={PATCH} />);

    expect(screen.getByText(/2 functions and 1 class/i)).toBeInTheDocument();
    expect(screen.getByText(/return hints to 1 function\b/i)).toBeInTheDocument();
  });

  it("names each edited symbol and where it landed", () => {
    render(<WhatChangedPane changes={CHANGES} patch={PATCH} />);

    expect(screen.getByText(/Widget/)).toBeInTheDocument();
    expect(screen.getByText(/line 12/i)).toBeInTheDocument();
  });

  it("says the edits are not applied", () => {
    render(<WhatChangedPane changes={CHANGES} patch={PATCH} />);

    expect(screen.getByText(/have not been applied/i)).toBeInTheDocument();
  });

  it("keeps the raw diff, collapsed", async () => {
    const user = userEvent.setup();
    render(<WhatChangedPane changes={CHANGES} patch={PATCH} />);

    const trigger = screen.getByRole("button", { name: /raw diff/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await user.click(trigger);

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/\+def hello\(\) -> None:/)).toBeInTheDocument();
  });

  it("explains a scan recorded before change tracking, and shows its diff", () => {
    render(<WhatChangedPane changes={[]} patch={PATCH} />);

    expect(screen.getByText(/before change tracking/i)).toBeInTheDocument();
    expect(screen.getByText(/\+def hello\(\) -> None:/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /raw diff/i })).not.toBeInTheDocument();
  });

  it("renders nothing when there is neither a change list nor a diff", () => {
    const { container } = render(<WhatChangedPane changes={[]} patch={null} />);

    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```
cd D:\ETPROJECT\frontend
npx vitest run src/components/WhatChangedPane.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 3: Create the component**

`frontend/src/components/WhatChangedPane.tsx`:

```tsx
import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { CodeViewer } from "@/components/CodeViewer";
import { cn } from "@/lib/utils";
import type { RefactorChange } from "@/lib/types";

interface WhatChangedPaneProps {
  changes: RefactorChange[];
  patch: string | null;
}

function count(n: number, singular: string, plural: string) {
  return `${n} ${n === 1 ? singular : plural}`;
}

/**
 * F5. This tab used to render the unified diff and nothing else, which asks the
 * reader to reconstruct the intent from +/- lines. The prose is built from the
 * engine's own change records, so it cannot disagree with the highlighting in
 * the pane beside it — both read the same list.
 *
 * The diff is not thrown away; it moves behind a disclosure. A scan recorded
 * before J3 has no change list, and gets told so rather than having prose
 * invented for it by re-parsing the diff.
 */
export function WhatChangedPane({ changes, patch }: WhatChangedPaneProps) {
  const [rawOpen, setRawOpen] = useState(false);

  if (changes.length === 0 && !patch) return null;

  if (changes.length === 0) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">
          This scan was recorded before change tracking, so there is no itemised list for it.
          The raw diff it captured is below.
        </p>
        <div className="bg-background border border-border/50 rounded-lg overflow-x-auto overflow-y-auto max-h-[600px] py-4 shadow-inner">
          <CodeViewer code={patch as string} isPatch />
        </div>
      </div>
    );
  }

  const docFunctions = changes.filter((c) => c.kind === "docstring" && c.target === "function");
  const docClasses = changes.filter((c) => c.kind === "docstring" && c.target === "class");
  const hints = changes.filter((c) => c.kind === "return_hint");

  const docTargets = [
    docFunctions.length > 0 ? count(docFunctions.length, "function", "functions") : null,
    docClasses.length > 0 ? count(docClasses.length, "class", "classes") : null,
  ].filter(Boolean);

  return (
    <div className="space-y-4 text-sm">
      {docTargets.length > 0 && (
        <section>
          <p className="font-medium text-foreground">
            Added placeholder docstrings to {docTargets.join(" and ")}.
          </p>
          <p className="mt-1 text-muted-foreground">
            Each of these had no docstring at all. The inserted text names the symbol and
            lists its parameters — it records the gap, it does not describe the behaviour.
          </p>
          <ul className="mt-2 space-y-1 text-muted-foreground">
            {[...docFunctions, ...docClasses].map((c, i) => (
              <li key={`doc-${i}`}>
                <code className="text-foreground">{c.name}</code> ({c.target}) — line {c.line}
              </li>
            ))}
          </ul>
        </section>
      )}

      {hints.length > 0 && (
        <section>
          <p className="font-medium text-foreground">
            Added <code>&rarr; None</code> return hints to {count(hints.length, "function", "functions")}.
          </p>
          <p className="mt-1 text-muted-foreground">
            These functions never return a value, so the hint states a contract the code
            already follows.
          </p>
          <ul className="mt-2 space-y-1 text-muted-foreground">
            {hints.map((c, i) => (
              <li key={`hint-${i}`}>
                <code className="text-foreground">{c.name}</code> — line {c.line}
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="text-xs text-muted-foreground">
        These edits are suggestions and have not been applied to the repository.
      </p>

      {patch && (
        <Collapsible open={rawOpen} onOpenChange={setRawOpen}>
          <CollapsibleTrigger className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground">
            <ChevronDown className={cn("w-4 h-4 transition-transform", rawOpen && "rotate-180")} aria-hidden="true" />
            View raw diff
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="mt-2 bg-background border border-border/50 rounded-lg overflow-x-auto overflow-y-auto max-h-[600px] py-4 shadow-inner">
              <CodeViewer code={patch} isPatch />
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

```
cd D:\ETPROJECT\frontend
npx vitest run src/components/WhatChangedPane.test.tsx
```

Expected: 6 passed. If the collapsed content is present in the DOM before the
click (Radix keeps mounted content in some configurations), assert on
`aria-expanded` alone rather than loosening the test — and say so in the commit.

- [ ] **Step 5: Wire it into the page**

In `frontend/src/pages/FileAnalysis.tsx`, add the import:

```tsx
import { WhatChangedPane } from "@/components/WhatChangedPane";
```

Replace the patch trigger and content. The tab now appears when there is either
a change list or a diff:

```tsx
                    {((file.refactorChanges?.length ?? 0) > 0 || file.patch) && (
                      <TabsTrigger value="changed">What changed</TabsTrigger>
                    )}
```

```tsx
                  {((file.refactorChanges?.length ?? 0) > 0 || file.patch) && (
                    <TabsContent value="changed" className="min-w-0">
                      <WhatChangedPane changes={file.refactorChanges ?? []} patch={file.patch} />
                    </TabsContent>
                  )}
```

- [ ] **Step 6: Verify**

```
cd D:\ETPROJECT\frontend
npm test
npm run typecheck
npm run build
```

Expected: 90 passed (84 + 6), typecheck exit 0, build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/WhatChangedPane.tsx frontend/src/components/WhatChangedPane.test.tsx frontend/src/pages/FileAnalysis.tsx
git commit -F <commit-message-file>
```

```
Replace the raw patch pane with an account of what changed

The tab rendered a unified diff and left the reader to reconstruct the intent
from +/- lines. It now reads the engine's change records: what was added, to
which symbols, on which lines, and why each transform fires at all. Because the
prose and the highlighting in the neighbouring pane come from the same list,
they cannot disagree.

The diff is still there, behind a disclosure. Scans recorded before change
tracking have no list to read, so they say so and show their diff outright
rather than having prose reverse-engineered from it.
```

---

### Task 7: Demo data, end-to-end, and the record

**Files:**
- Modify: `frontend/src/lib/mock-data.ts` (the file at `:67-83` gets changes; the one at `:255` keeps none)
- Create: `frontend/src/pages/FileAnalysis.test.tsx`
- Modify: `frontend/e2e/findings.spec.ts`
- Modify: `docs/DECISIONS.md`, `docs/HANDOVER.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Give the demo both states**

In `frontend/src/lib/mock-data.ts`, add to the first file (the one with
`improved_code` and a `patch`, around `:67-83`) a `refactorChanges` array whose
line numbers **point at real lines of that file's `improved_code`**. Open the
string, count the lines, and pick the ones that are actually docstrings:

```ts
      refactorChanges: [
        { kind: "docstring", target: "function", name: "process_data", line: 2, lineCount: 1 },
        { kind: "docstring", target: "function", name: "validate_item", line: 7, lineCount: 1 },
      ],
```

Those two numbers were counted against the existing `improved_code` string
while writing this plan: line 2 is `"""Process and validate input data
items."""` and line 7 is `"""Validate a single data item."""`. **Re-count them
if you touch that string** — a highlight pointing at the wrong line is worse
than no highlight, and the demo is the only place a reader meets this feature
without running a scan. Leave the file at `:255`
(`improved_code: ""`) without the field, so the demo carries the empty state too.

- [ ] **Step 2: Write the page test**

Create `frontend/src/pages/FileAnalysis.test.tsx`. The harness is the one
`IssueExplorer.test.tsx` uses: mock the scan context module, feed it a report,
render the default export directly. No router wrapper is used there:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ScanReport } from "@/lib/types";

const mockUseScan = vi.fn();
vi.mock("@/context/ScanContext", () => ({ useScan: () => mockUseScan() }));

import FileAnalysis from "./FileAnalysis";

const WITH_EDITS = {
  name: "main.py",
  path: "src/main.py",
  fileType: "production",
  issues: [],
  security: [],
  suggestions: [],
  explanation: "",
  original_code: 'def hello():\n    print("x")',
  improved_code: 'def hello() -> None:\n    """Hello."""\n    print("x")',
  patch: "--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@\n-def hello():\n+def hello() -> None:",
  refactorChanges: [
    { kind: "return_hint", target: "function", name: "hello", line: 1, lineCount: 1 },
    { kind: "docstring", target: "function", name: "hello", line: 2, lineCount: 1 },
  ],
};

const WITHOUT_EDITS = {
  name: "clean.py",
  path: "src/clean.py",
  fileType: "production",
  issues: [],
  security: [],
  suggestions: [],
  explanation: "",
  original_code: 'def done() -> None:\n    """Done."""\n    print("x")',
  improved_code: "",
  patch: null,
  refactorChanges: [],
};

function renderWith(files: unknown[]) {
  mockUseScan.mockReturnValue({ currentReport: { files } as unknown as ScanReport });
  return render(<FileAnalysis />);
}

describe("FileAnalysis code panes", () => {
  it("labels the pane for what the engine actually does", () => {
    renderWith([WITH_EDITS]);

    expect(screen.getByRole("tab", { name: "Suggested edits" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Improved" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Patch" })).not.toBeInTheDocument();
  });

  it("offers the what-changed tab for a file that has edits", () => {
    renderWith([WITH_EDITS]);

    expect(screen.getByRole("tab", { name: "What changed" })).toBeInTheDocument();
  });

  it("explains the empty state for a file with no suggested edits", () => {
    renderWith([WITHOUT_EDITS]);

    fireEvent.click(screen.getByRole("tab", { name: "Suggested edits" }));

    expect(screen.getByText(/Nothing to suggest here/i)).toBeInTheDocument();
  });
});
```

`FileAnalysis` selects a file from the report — if it renders no file until one
is chosen, click the file in the sidebar first (its name is in the fixture) and
say so in the commit. Do not weaken an assertion to route around that.

- [ ] **Step 3: Run it, watching it fail first if you write it before wiring**

```
cd D:\ETPROJECT\frontend
npx vitest run src/pages/FileAnalysis.test.tsx
```

Expected: PASS once written against the wired page. If the "Improved" assertion
passes trivially, confirm you are looking at the right tab strip.

- [ ] **Step 4: Add the end-to-end assertion**

Append to `frontend/e2e/findings.spec.ts`, following that file's existing
`loadDemo` / `navigateTo` idiom and its rule about waiting for the destination
page's own heading before querying anything:

```ts
/**
 * J3. The panes are the product's explanation surface; a unit test can prove
 * the component renders, only the real app proves the demo reaches it.
 */
test("the suggested-edits pane names its checks and the diff stays reachable", async ({ page }) => {
  await loadDemo(page);
  await navigateTo(page, "/file-analysis");

  // Wait for the page's own heading before querying anything, per the note at
  // the top of this file — a selector built before that can lock onto the
  // previous route's DOM. Then select a demo file, open "What changed", and:
  await expect(page.getByRole("tab", { name: "Suggested edits" })).toBeVisible();

  await page.getByRole("tab", { name: "What changed" }).click();
  await expect(page.getByRole("button", { name: /raw diff/i })).toBeVisible();
});
```

The route is `/file-analysis` — confirmed in `frontend/src/lib/routes.ts:84`,
which is the single route table. Do not hardcode a path that is not in it.

- [ ] **Step 5: Run the full verification set**

```
cd D:\ETPROJECT\frontend
npm test
npm run typecheck
npm run build
npx playwright test
```

```
D:\ETPROJECT\venv\Scripts\python.exe -m pytest backend/tests -q
```

Expected: vitest > 90 passed 0 failed; typecheck exit 0; build succeeds;
Playwright ≥ 23 passed 0 failed; pytest ≥ 440 passed 0 failed. **Record every
count.** A Playwright run that fails only under parallelism has precedent here
(J1 saw three such failures) — if one fails, re-run that project alone before
calling it a regression, and report both runs.

- [ ] **Step 6: Write the decision record**

Append to `docs/DECISIONS.md` a new decision, numbered **after checking the
highest number actually present**. Note that the file currently has **two**
sections numbered D17 (a `###` breakpoint ruling around line 330 and the `##`
J1 record around line 362). Before renumbering either, `grep -rn "D17" docs/`
to see which is referenced elsewhere; `HANDOVER.md` points at the J1 one. Fix
the numbering minimally, so no existing reference breaks.

The new record covers: the change list as one source for three consumers; why
the `explanation` append was rebuilt rather than deleted (three readers); the
`// 2` defect and what it produced; and the "Improved" → "Suggested edits"
rename as a copy-honesty fix in the J1 lineage.

- [ ] **Step 7: Update the handover**

In `docs/HANDOVER.md`: section 1's status line and git state, the phase table
row for J, and section 2's evidence table with this session's fresh counts and
the session id. Phase J is complete after this; the next unstarted items are F1
and Phase M.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/mock-data.ts frontend/src/pages/FileAnalysis.test.tsx frontend/e2e/findings.spec.ts docs/DECISIONS.md docs/HANDOVER.md
git commit -F <commit-message-file>
```

```
Close J3: demo both pane states and record the decision

The demo is where anyone meets this feature without running a scan, so one
demo file now carries a change list and another carries none, putting both the
highlighted and the empty state on screen. Adds the page's first test file and
one end-to-end pass over the real app.

Records why the change list is the single source for the summary sentence, the
highlighting and the prose, and why the pane stopped calling its output
"Improved".
```

Then `git status --short` and delete any junk.

---

## Definition of done

Every row run fresh in the implementing session, with the output recorded:

| Check | Bar |
|---|---|
| `venv\Scripts\python.exe -m pytest backend/tests -q` | ≥ 440 passed, 0 failed |
| `npm test` (from `frontend/`) | > 90 passed, 0 failed |
| `npm run typecheck` | exit 0 |
| `npm run build` | succeeds |
| `npx playwright test` | ≥ 23 passed, 0 failed |
| `git status --short` | clean, no junk files |

Plus the acceptance criterion that is not a test: **run a real scan and open the
File Analysis page.** A file with suggested edits must show highlights on the
lines the engine actually changed, and a file without them must show the empty
state naming both checks. The unit tests use hand-built fixtures; only a real
scan proves the line numbers survive the whole pipeline.
