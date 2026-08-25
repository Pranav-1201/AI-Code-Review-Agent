# J3 — the code panes (F4, F5)

**Date:** 2026-08-25 · **Author:** Pranav Upadhyay · **Model:** Claude Opus 5,
session `e4ebf578` · **Phase:** J3, the last part of Phase J
**Status:** approved in chat, not yet implemented

---

## 1. What this closes

Two ideas from `docs/STAFF_AUDIT_2026-08-19.md`, both rated **H × M**:

| Idea | Text in the audit |
|---|---|
| F4 | "Improved" pane: say *"No improvements needed"* when empty; otherwise show the **full** improved file with changed regions highlighted |
| F5 | Replace the raw patch pane with a prose explanation of *what* changed and *why* |

Both were carried into J3 by the J1 decision record, which fixed the two design
questions in advance:

> F5's prose comes from a structured change list replacing the string-counting at
> `heuristic_refactor_engine.py:265-281` (which counts `"""` occurrences ÷ 2 and
> miscounts single-line docstrings), and F4's empty state says what was actually
> checked rather than implying a clean bill of health.

This spec keeps both rulings and does not re-litigate them.

---

## 2. What the engine actually does today

This matters, because the panes have been overstating it.

`backend/app/analysis/heuristic_refactor_engine.py` applies exactly two AST
transforms, in this order:

1. `_add_missing_docstrings` — inserts a **placeholder** docstring above the
   body of any function, async function or class that lacks one. The text is
   generated from the name (`"""Process data."""`), or for a function with
   parameters, a multi-line block with an `Args:` section listing each parameter
   as `name: Description.`
2. `_add_type_hints_to_simple_functions` — appends `-> None` to the `def` line of
   any function with no annotated return and no `return <value>` anywhere in its
   body.

Nothing else. No restructuring, no complexity reduction, no security fix. The
complexity- and smell-driven strings in the same method are *suggestions*
(`suggestions[]`), never applied to `improved_code`.

The pane is currently labelled **"Improved"**. That claims a quality judgement
the engine never makes, in the same way the AI Suggestions subtitle claimed
"AI-generated" over "Rule-based" badges before J1 corrected it (CONSTRAINTS 18
governs this class of copy). The label becomes **"Suggested edits"**.

### The defect in the current prose

`heuristic_refactor_engine.py:265-281` derives its summary by counting strings:

```python
added_docstrings = sum(1 for l in impr_lines if '"""' in l) - sum(1 for l in orig_lines if '"""' in l)
...
changes.append(f"Added docstrings to {added_docstrings // 2} undocumented function(s)/class(es)")
```

The `// 2` assumes every docstring spans two lines carrying `"""`. The engine
emits a **single-line** docstring for any function without parameters and for
every class — `"""Class Foo."""` — which contributes `1`, so `1 // 2 == 0` and
the summary silently reports nothing was added. A file whose only gaps are
parameterless functions gets an accurate-looking sentence claiming zero changes
while the pane beside it shows the inserted docstrings.

---

## 3. Design

### 3.1 The change list is the single source

Both transforms return `(code, changes)` rather than `code`. A change record:

```python
{
    "kind": "docstring" | "return_hint",
    "target": "function" | "class",
    "name": "process_data",
    "line": 12,        # 1-based, in the IMPROVED file
    "line_count": 5,   # improved-file lines this change occupies
}
```

`generate_refactor` concatenates both lists and returns them as `"changes"`.

**Line coordinates.** `line` must be the line in the file the pane renders, not
in the original, or the highlight is off by the number of lines inserted above
it. The docstring pass currently inserts in reverse order into a list of source
lines; it will instead sort insertions ascending and carry a running offset, so
each record's `line` accounts for every insertion above it. The return-hint pass
re-parses the already-docstringed code, so the `def` lines it sees are already
in improved coordinates, and it replaces in place without changing the line
count — its records need no adjustment and do not invalidate the docstring
records computed before them.

A `line_count` greater than 1 occurs only for the parameterised multi-line
docstring form.

### 3.2 The summary line stays where it is, but becomes true

The append at `:265-281` currently writes into `explanation`, which is read in
**three** places, not one:

- `FileAnalysis.tsx:256` — the Explanation card
- `AISuggestions.tsx:41-49`
- `ExportReport.tsx:41`

So the append is not deleted — deleting it would silently strip content from two
pages J3 was not asked to touch. It is rebuilt from the change list, which fixes
the miscount everywhere it appears. The new pane carries per-item detail; the
card keeps the one-line summary.

### 3.3 Contract

`repository_review_engine.py`'s `final_output` gains one key:

```python
"refactor_changes": refactor_result.get("changes", []),
```

Additive and optional. Scans persisted before this change simply lack it, and
`services/pr_review_engine.py` — the other caller of the engine — reads named
keys and is unaffected by a new one.

Frontend:

```ts
export interface RefactorChange {
  kind: "docstring" | "return_hint";
  target: "function" | "class";
  name: string;
  line: number;       // 1-based, improved file
  lineCount: number;
}
```

`FileRecord` gains `refactorChanges?: RefactorChange[]`. `response-mapper.ts`
normalizes the array at the boundary and drops malformed entries, following the
precedent `normalizeVulnerabilities` already set for pre-OSV records: a bad
shape is neutralised where it enters, not guarded at every consumer.

### 3.4 F4 — the "Suggested edits" pane

Two states.

**Nothing to suggest** (`improved_code` empty, equal to the original, or an
empty change list). The copy names what was checked and refuses to imply more:

> Nothing to suggest here. Two checks ran against this file: functions and
> classes with no docstring, and functions that never return a value but have no
> `-> None` hint. This file has neither gap. No other transform was attempted —
> this is not a clean bill of health.

**Has edits.** The full improved file renders, with lines
`line … line + line_count - 1` highlighted for every change. Colour is not the
only cue — changed lines carry a gutter marker and the region carries a count
legend, per the accessibility bar F16 set in J2.

### 3.5 F5 — the "What changed" pane

Replaces the Patch tab. Prose is built from the change list:

- "Added placeholder docstrings to 3 functions and 1 class", then each item by
  name and line
- "Added `-> None` return hints to 2 functions", likewise

The raw unified diff is not discarded — it sits inside a collapsed disclosure
within the same pane, so the exact patch stays reachable while the default view
is the readable one.

**Pre-J3 scans** carry a `patch` string and no change list. The pane says the
scan predates change tracking and renders the diff uncollapsed, rather than
fabricating prose by re-parsing a rendered artifact.

---

## 4. Testing

**A fixture that passes both before and after a fix measures nothing.** Every
test added here is watched failing against the pre-change engine first — the
discipline Phase G's acceptance criteria recorded after the gate read 1.00
across the board while every security finding on flask was wrong.

Backend:

- Change records are emitted for a function docstring, a class docstring, a
  parameterised multi-line docstring and a `-> None` hint.
- **The line number is asserted against the improved text**, not against a
  count: `improved.splitlines()[line - 1]` contains the inserted docstring. A
  count assertion cannot see an off-by-one; this can.
- The single-line-docstring case that `// 2` silently zeroed is pinned
  explicitly.
- A file with no gaps returns an empty change list and an unchanged summary.

Frontend:

- `frontend/src/pages/FileAnalysis.test.tsx` — the page has **no** test file
  today, so this is a new file, not an edit. Covers: the empty state's text, the
  exact set of highlighted lines, the prose counts, and the pre-J3 fallback.
- `mock-data.ts` gains `refactor_changes` on one demo file and none on another,
  so the demo route exercises both states.
- One Playwright assertion over the demo.

Acceptance, all run fresh in the implementing session, against these baselines
measured in session `e4ebf578` before any change:

| Check | Baseline | Bar |
|---|---|---|
| `venv\Scripts\python.exe -m pytest backend/tests -q` | 432 passed, 0 failed | ≥ 432, 0 failed |
| `npm test` (vitest) | 70 passed, 11 files | > 70, 0 failed |
| `npm run typecheck` (`tsc -b`) | — | exit 0 |
| `npm run build` | — | succeeds |
| `npx playwright test` | — | ≥ baseline, 0 failed |

`tsc --noEmit` is not an acceptable substitute for `npm run typecheck` here: the
frontend tsconfig is solution-style, so `--noEmit` compiles an empty program and
exits 0 (D16).

---

## 5. Out of scope, flagged not fixed

- **`generate_improved_code` is a dead toggle.** `settings_manager.py:43`
  defaults it to `True` and `Settings.tsx:236` renders a switch for it, but no
  code reads it — the transforms run unconditionally. Changing that alters scan
  behaviour and belongs in its own change.
- **`DECISIONS.md` has two sections numbered D17** (line 330, the breakpoint
  ruling; line 362, the J1 record). Corrected as a documentation fix at session
  end, not inside a task.
- F1 (light mode) and Phase M (deploy) are untouched.
