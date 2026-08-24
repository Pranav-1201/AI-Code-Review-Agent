# J2 — Finding Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every finding a real code snippet, collapse the finding cards so a 600-finding report is scannable, and make the Security Report severity tiles navigate to the findings they count.

**Architecture:** One new stdlib-only backend helper (`extract_snippet`) is called by the two places that currently emit a placeholder string, so the `snippet` field starts carrying real source. The frontend then carries that field through `FindingView` — filtering the legacy placeholder shape, because 523 cached scans still contain it — and renders it inside a Radix `Collapsible` panel that is closed by default. Security Report groups its flat list by severity and wires its tiles to those groups.

**Tech Stack:** Python 3 stdlib (backend, no new packages); React 18 + TypeScript, Radix `Collapsible` (already vendored at `frontend/src/components/ui/collapsible.tsx`), Tailwind, vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-20-j2-finding-detail-design.md`

## Global Constraints

- **Interpreter is `venv\Scripts\python.exe` at the repo root**, never `backend/venv`, never global `python`. Global Python 3.13 has no fastapi and dies at collection.
- **Run all frontend commands from `D:\ETPROJECT\frontend`.** The Bash tool's working directory persists between calls — use absolute paths or `cd` in the same command.
- **Typecheck with `npm run typecheck` (`tsc -b`), never `tsc --noEmit`.** `frontend/tsconfig.json` is solution-style (`"files": []` plus `references`), so `--noEmit` compiles an empty program and exits 0 having checked nothing.
- **Never `git add -A` / `git add .`** Stage explicit paths only. The tree carries a gitignored `.env`, `backend/app/.cache/`, and stray zero-byte junk files.
- **Run `git status --short` after every commit** and delete any zero-byte junk file that appears. Verify it is 0 bytes before deleting.
- **No new runtime dependency.** `@radix-ui/react-collapsible` is already installed and vendored. Adding any other package requires asking first (`docs/CONSTRAINTS.md` §7).
- **No AI attribution in any commit message.** No `Co-Authored-By`, no "Generated with". Repo voice: what changed and why.
- **One logical change per commit.** Each task below is one commit.
- **Exclude `backend/app/.cache/` from every recursive grep.** It holds 523 cached scan JSONs and returns megabytes.
- Baseline measured at plan time, this session: **vitest 59 passed / 11 files**. Backend floor from `docs/HANDOVER.md`: **417 passed**.

---

### Task 1: `extract_snippet` — the helper, alone

**Files:**
- Create: `backend/app/services/snippet.py`
- Test: `backend/tests/test_snippet.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `extract_snippet(source_lines: list[str], line: int, context: int = 2) -> str`, and the module constant `MAX_LINE_CHARS = 200`. Task 2 imports `extract_snippet` from `app.services.snippet`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_snippet.py`:

```python
"""Unit tests for the snippet extractor.

The point of this module is that a finding can show its evidence. The tests
that matter most are the ones asserting it returns "" rather than a sentence
when there is no evidence — the field it replaces used to emit
"Line 481 indicates: Command Injection" whether or not any source was known.
"""

from app.services.snippet import MAX_LINE_CHARS, extract_snippet

SOURCE = [
    "import subprocess",
    "",
    "",
    "class Runner:",
    "    def run(self, cmd):",
    "        if cmd:",
    "            subprocess.run(cmd, shell=True)",
    "        return None",
]


def test_returns_the_flagged_line_with_two_lines_of_context():
    out = extract_snippet(SOURCE, 7)

    # Line 7 is the subprocess call; 5..9 clipped to 5..8 by the file end.
    assert out.splitlines() == [
        "5: def run(self, cmd):",
        "6:     if cmd:",
        "7:         subprocess.run(cmd, shell=True)",
        "8:     return None",
    ]


def test_strips_the_common_indent_but_keeps_relative_indent():
    out = extract_snippet(SOURCE, 7)

    # The window's shallowest non-blank line is `def run` at 4 spaces, so 4
    # come off every line and `subprocess.run` keeps the 4 that remain.
    assert "5: def run(self, cmd):" in out
    assert "7:         subprocess.run(cmd, shell=True)" in out


def test_clamps_at_the_first_line():
    out = extract_snippet(SOURCE, 1)

    assert out.splitlines() == [
        "1: import subprocess",
        "2: ",
        "3: ",
    ]


def test_clamps_at_the_last_line():
    out = extract_snippet(SOURCE, 8)

    assert out.splitlines() == [
        "6: if cmd:",
        "7:     subprocess.run(cmd, shell=True)",
        "8: return None",
    ]


def test_truncates_a_very_long_line():
    out = extract_snippet(["x = " + "a" * 500], 1)

    body = out.split(": ", 1)[1]
    assert len(body) == MAX_LINE_CHARS + 1  # the cap plus the ellipsis
    assert body.endswith("\u2026")


def test_returns_empty_string_when_there_is_no_source():
    assert extract_snippet([], 5) == ""


def test_returns_empty_string_when_the_line_is_out_of_range():
    assert extract_snippet(SOURCE, 99) == ""


def test_returns_empty_string_for_a_zero_or_negative_line():
    # `line` defaults to 0 all over the analyzer for "position unknown".
    assert extract_snippet(SOURCE, 0) == ""
    assert extract_snippet(SOURCE, -3) == ""


def test_context_width_is_adjustable():
    out = extract_snippet(SOURCE, 7, context=1)

    assert out.splitlines() == [
        "6: if cmd:",
        "7:     subprocess.run(cmd, shell=True)",
        "8: return None",
    ]
```

- [ ] **Step 2: Run the test and verify it fails**

Run from `D:\ETPROJECT`:

```
venv\Scripts\python.exe -m pytest backend/tests/test_snippet.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'app.services.snippet'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/services/snippet.py`:

```python
"""Extract the source behind a finding.

A finding that names a line and shows nothing asks the reader to trust it.
This turns a (source, line) pair into a short, self-locating excerpt.

Deliberately stdlib-only and free of any analyzer import: two unrelated call
sites need it — the per-file security analyzer and the inter-procedural taint
pass — and neither should have to import the other to get it.
"""

from __future__ import annotations

# Minified and generated sources have single lines thousands of characters
# long. Uncapped they would bloat every cached scan and blow out the layout of
# the pane that renders them.
MAX_LINE_CHARS = 200


def extract_snippet(source_lines: list[str], line: int, context: int = 2) -> str:
    """Return `line` plus `context` lines either side, numbered and dedented.

    Returns "" when there is nothing to show — no source, or a line outside
    the file. It never returns a sentence: absent evidence is rendered as
    absent by the UI, and a placeholder string defeats that.
    """
    if not source_lines or line <= 0 or line > len(source_lines):
        return ""

    start = max(0, line - 1 - context)          # 0-based, inclusive
    end = min(len(source_lines), line + context)  # 0-based, exclusive
    window = source_lines[start:end]

    # Strip the indent shared by the whole window, so an excerpt from deep
    # inside a class does not render as a column of whitespace. Blank lines
    # carry no indent information and must not drag the common prefix to 0.
    indents = [len(raw) - len(raw.lstrip()) for raw in window if raw.strip()]
    shared = min(indents) if indents else 0

    out = []
    for number, raw in enumerate(window, start=start + 1):
        text = raw[shared:]
        if len(text) > MAX_LINE_CHARS:
            text = text[:MAX_LINE_CHARS] + "\u2026"
        out.append(f"{number}: {text}")

    return "\n".join(out)
```

- [ ] **Step 4: Run the test and verify it passes**

```
venv\Scripts\python.exe -m pytest backend/tests/test_snippet.py -q
```

Expected: `9 passed`. **Read the count, not just the exit code** — a run that collected 0 tests also exits 0.

- [ ] **Step 5: Commit**

```bash
cd D:/ETPROJECT
git add backend/app/services/snippet.py backend/tests/test_snippet.py
git commit -m "Add a source-snippet extractor for findings"
git status --short
```

Delete any zero-byte junk file `git status` reports (verify 0 bytes with `wc -c` first).

---

### Task 2: Both producers emit real source

**Files:**
- Modify: `backend/app/services/security_analyzer.py` — the `snippet` line at the end of `_add_issue` (search for `indicates:`)
- Modify: `backend/app/services/repository_review_engine.py` — the two `"snippet": f"Line {f.line}"` literals inside `apply_interprocedural_taint`
- Test: `backend/tests/test_snippet_wiring.py` (create)

**Interfaces:**
- Consumes: `extract_snippet` from Task 1.
- Produces: findings whose `snippet` value is either numbered source lines or `""`. Task 3's frontend filter depends on real snippets **never** matching `/^Line \d+( indicates: .+)?$/`.

**Context you need:** `SecurityAnalyzer.__init__` already stores `self._source_lines` (`security_analyzer.py:194`, `source.splitlines()`). `apply_interprocedural_taint` already builds `sources = {r["file_path"]: r.get("content", "")}` near `repository_review_engine.py:305`. Neither site needs new plumbing — the source is already in scope.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_snippet_wiring.py`:

```python
"""The two producers that used to emit a placeholder now emit real source.

`docs/HANDOVER.md` records the rule these tests exist to satisfy: a fixture
that passes both before and after a change is measuring nothing. Step 2 of
this task runs these against the unmodified analyzer and they must fail.
"""

import re

from app.services.security_analyzer import SecurityAnalyzer

LEGACY = re.compile(r"^Line \d+( indicates: .+)?$")

VULNERABLE = '''import subprocess


def handler(request):
    cmd = request.args.get("cmd")
    subprocess.run(cmd, shell=True)
'''


def _security_issues(source: str, path: str = "app/handler.py"):
    analyzer = SecurityAnalyzer(file_path=path, source=source)
    import ast
    analyzer.bind_imports(ast.parse(source))
    analyzer.visit(ast.parse(source))
    return analyzer.issues


def test_a_finding_carries_the_source_that_triggered_it():
    issues = _security_issues(VULNERABLE)
    assert issues, "expected at least one security finding on this source"

    snippet = issues[0]["snippet"]

    assert "subprocess.run" in snippet
    assert not LEGACY.match(snippet), f"still the placeholder shape: {snippet!r}"


def test_the_snippet_is_line_numbered():
    issues = _security_issues(VULNERABLE)

    snippet = issues[0]["snippet"]

    assert re.match(r"^\d+: ", snippet), f"not line-numbered: {snippet!r}"


def test_no_source_yields_an_empty_snippet_not_a_sentence():
    # The analyzer is constructible without source; findings from that path
    # must say nothing rather than restate their own line number.
    analyzer = SecurityAnalyzer(file_path="app/handler.py", source="")
    analyzer._add_issue("High", "Something", "Fix it", line=12, issue_type="Command Injection")

    assert analyzer.issues[0]["snippet"] == ""
```

**Note on the helper:** the two `ast.parse` calls and `bind_imports` mirror how `detect_security_issues` drives the analyzer. If the analyzer's real entry point has a different name in the tree you are working in, read it and call that instead — the assertions are the point, not the plumbing.

- [ ] **Step 2: Run the test against the UNMODIFIED analyzer and verify it fails**

```
venv\Scripts\python.exe -m pytest backend/tests/test_snippet_wiring.py -q
```

Expected: **FAIL**, with the snippet reported as `'Line 6 indicates: Command Injection'`.

This step is not optional. If these tests pass before the change, they are measuring nothing and the task's evidence is worthless.

- [ ] **Step 3: Wire `security_analyzer.py`**

Add the import at the top of the file, beside the other `app.services` imports:

```python
from app.services.snippet import extract_snippet
```

Then, in `_add_issue`, replace:

```python
            "snippet": f"Line {line} indicates: {issue_type}"  # Simplified without full tree mapping
```

with:

```python
            # Real evidence, not a restatement of the line number. Empty when
            # the analyzer was constructed without source (see snippet.py).
            "snippet": extract_snippet(self._source_lines, line),
```

- [ ] **Step 4: Wire `repository_review_engine.py`**

Add to the imports at the top:

```python
from app.services.snippet import extract_snippet
```

Inside `apply_interprocedural_taint`, the `sources` dict is already built. Immediately after the `for f in findings:` loop resolves `r`, derive the lines once:

```python
        finding_source = (sources.get(f.file) or sources.get(f.file.replace("\\", "/")) or "")
        finding_lines = finding_source.splitlines()
```

Then replace **both** occurrences of:

```python
                "snippet": f"Line {f.line}",
```

with:

```python
                "snippet": extract_snippet(finding_lines, f.line),
```

There are two — one in the `risks.append({...})` block and one in the `issues.append({...})` block. Search for `f"Line {f.line}"` and confirm zero remain.

- [ ] **Step 5: Run the wiring test and verify it passes**

```
venv\Scripts\python.exe -m pytest backend/tests/test_snippet_wiring.py -q
```

Expected: `3 passed`.

- [ ] **Step 6: Run the whole backend suite**

```
venv\Scripts\python.exe -m pytest backend/tests -q
```

Expected: **≥ 429 passed, 0 failed** (the 417 floor plus Task 1's 9 and this task's 3). Read the count.

If anything fails, it is most likely a test that asserted on the old placeholder string. Search for `indicates:` under `backend/tests/` and update the assertion to the new contract — do not revert the change to satisfy a test that pins the defect.

- [ ] **Step 7: Commit**

```bash
cd D:/ETPROJECT
git add backend/app/services/security_analyzer.py backend/app/services/repository_review_engine.py backend/tests/test_snippet_wiring.py
git commit -m "Emit the flagged source with security findings

The snippet field carried f\"Line {line} indicates: {type}\" — a restatement
of the line number the finding already reports. Both producers already had
the source in scope, so they now slice it."
git status --short
```

---

### Task 3: Carry `snippet` to the view, filtering the legacy shape

**Files:**
- Modify: `frontend/src/lib/findings.ts`
- Test: `frontend/src/lib/findings.test.ts` (create)

**Interfaces:**
- Consumes: the backend contract from Task 2.
- Produces: `FindingView.snippet?: string`. Tasks 4 and 5 render it.

**Why the filter is mandatory:** `backend/app/.cache/` holds 523 cached scans, all predating Task 2, and `ScanHistory` replays them. Every one carries the placeholder. Without the filter, shipping J2 gives every historical report a code pane reading `Line 481 indicates: Command Injection`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/findings.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { fromFileIssue, fromSecurityVulnerability } from "./findings";
import type { FileAnalysis, FileIssue, SecurityVulnerability } from "./types";

const file = { name: "runner.py", path: "backend/app/runner.py" } as FileAnalysis;

const vuln = (snippet?: string): SecurityVulnerability => ({
  type: "Command Injection",
  severity: "Critical",
  description: "shell=True with a request value",
  file: "backend/app/runner.py",
  line: 42,
  snippet,
});

const issue = (snippet?: string): FileIssue => ({
  message: "Function exceeds recommended length",
  severity: "Medium",
  category: "maintainability",
  line: 42,
  snippet,
});

describe("snippet handling", () => {
  it("carries a real snippet through to the view", () => {
    const code = "41:     cmd = request.args.get(\"cmd\")\n42:     subprocess.run(cmd, shell=True)";

    expect(fromSecurityVulnerability(vuln(code)).snippet).toBe(code);
    expect(fromFileIssue(issue(code), file).snippet).toBe(code);
  });

  // These are the exact two shapes found across the 523 cached scans in
  // backend/app/.cache/ — 271 findings carry the field and none carry code.
  it("drops the legacy placeholder that cached scans still contain", () => {
    expect(fromSecurityVulnerability(vuln("Line 481 indicates: Command Injection")).snippet)
      .toBeUndefined();
    expect(fromSecurityVulnerability(vuln("Line 42")).snippet).toBeUndefined();
    expect(fromFileIssue(issue("Line 7 indicates: SQL Injection"), file).snippet)
      .toBeUndefined();
  });

  it("treats an empty or whitespace snippet as absent", () => {
    expect(fromSecurityVulnerability(vuln("")).snippet).toBeUndefined();
    expect(fromSecurityVulnerability(vuln("   ")).snippet).toBeUndefined();
    expect(fromSecurityVulnerability(vuln(undefined)).snippet).toBeUndefined();
  });

  it("keeps code that merely starts with a number", () => {
    // A real snippet is always line-numbered, so it must not be mistaken for
    // the placeholder. "42: ..." has a colon and code after it; "Line 42"
    // does not.
    expect(fromSecurityVulnerability(vuln("42: return None")).snippet).toBe("42: return None");
  });
});
```

- [ ] **Step 2: Run the test and verify it fails**

```
cd D:/ETPROJECT/frontend && npx vitest run src/lib/findings.test.ts
```

Expected: FAIL — `snippet` is `undefined` in the first test because `FindingView` has no such property.

- [ ] **Step 3: Implement**

In `frontend/src/lib/findings.ts`, add to the `FindingView` interface, after `howToFix`:

```ts
  /** Numbered source lines around the finding. Absent when unknown. */
  snippet?: string;
```

Above the two mapper functions, add:

```ts
/**
 * The shape the backend emitted before J2: "Line 42" or
 * "Line 481 indicates: Command Injection". 523 cached scans still contain it
 * and ScanHistory replays them, so it is filtered here rather than rendered.
 * A real snippet is line-numbered as "42: <code>" and never matches this.
 */
const LEGACY_SNIPPET = /^Line \d+( indicates: .+)?$/;

function cleanSnippet(raw?: string): string | undefined {
  if (!raw) return undefined;
  const trimmed = raw.trim();
  if (!trimmed || LEGACY_SNIPPET.test(trimmed)) return undefined;
  return raw;
}
```

Then add `snippet: cleanSnippet(v.snippet),` to the object returned by `fromSecurityVulnerability`, and `snippet: cleanSnippet(i.snippet),` to the one returned by `fromFileIssue`.

- [ ] **Step 4: Run the test and verify it passes**

```
cd D:/ETPROJECT/frontend && npx vitest run src/lib/findings.test.ts
```

Expected: `4 passed`.

- [ ] **Step 5: Typecheck**

```
cd D:/ETPROJECT/frontend && npm run typecheck
```

Expected: exit 0. Remember: `npm run typecheck` runs `tsc -b`. Do not substitute `tsc --noEmit` — it checks nothing here.

- [ ] **Step 6: Commit**

```bash
cd D:/ETPROJECT
git add frontend/src/lib/findings.ts frontend/src/lib/findings.test.ts
git commit -m "Carry the finding snippet to the view, dropping the legacy shape

Cached scans predate the real snippet and all 271 of their snippet values
are placeholders like \"Line 481 indicates: Command Injection\". ScanHistory
replays those, so the mapper filters that shape instead of rendering it."
git status --short
```

---

### Task 4: `FindingCard` collapses, and shows the snippet when open

**Files:**
- Modify: `frontend/src/components/FindingCard.tsx`
- Modify: `frontend/src/components/FindingCard.test.tsx`
- Modify: `frontend/src/pages/SecurityReport.test.tsx`
- Modify: `frontend/src/pages/IssueExplorer.test.tsx`

**Interfaces:**
- Consumes: `FindingView.snippet` from Task 3; `Collapsible`, `CollapsibleTrigger`, `CollapsibleContent` from `@/components/ui/collapsible`.
- Produces: a card whose expandable region is toggled by a `<button>` exposing `aria-expanded`. Task 6's Playwright spec drives that button.

**This task breaks three existing test files, and that is expected.** Radix `CollapsibleContent` does not render its children while closed. `FindingCard.test.tsx`, `SecurityReport.test.tsx` and `IssueExplorer.test.tsx` all assert that why-it-matters and how-to-fix text is in the document immediately after render. Those assertions must expand the card first. Updating them is part of this task's commit — do not add `forceMount` to keep the old assertions passing, because that would defeat the point of collapsing.

- [ ] **Step 1: Write the failing test**

Replace the body of `frontend/src/components/FindingCard.test.tsx` with the following, keeping the existing `full` fixture at the top and adding `snippet` to it:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { FindingCard } from "./FindingCard";
import type { FindingView } from "@/lib/findings";

const full: FindingView = {
  title: "Command Injection",
  detail: "subprocess call with a non-constant argv[0]",
  severity: "Critical",
  category: "security",
  fileName: "runner.py",
  filePath: "backend/app/runner.py",
  line: 42,
  whyItMatters: "Attackers could run unauthorized utilities on the server.",
  howToFix: "Use subprocess.run([...]) with shell=False.",
  snippet: "41:     cmd = request.args.get(\"cmd\")\n42:     subprocess.run(cmd, shell=True)",
  confidence: 0.9,
  trustBoundary: "untrusted_input",
};

describe("FindingCard", () => {
  it("is collapsed by default, showing identity but not the explanation", () => {
    render(<FindingCard finding={full} />);

    // Visible while collapsed: what it is, how bad, and where.
    expect(screen.getByText("Command Injection")).toBeInTheDocument();
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("runner.py")).toBeInTheDocument();
    expect(screen.getByText("Line 42")).toBeInTheDocument();
    expect(screen.getByText("Untrusted input")).toBeInTheDocument();
    expect(screen.getByText("90% Match")).toBeInTheDocument();

    // Hidden until asked for.
    expect(screen.queryByText(/Attackers could run unauthorized utilities/)).toBeNull();
    expect(screen.queryByText(/Use subprocess.run/)).toBeNull();
  });

  it("exposes an expand control that reports its state", () => {
    render(<FindingCard finding={full} />);

    const trigger = screen.getByRole("button", { name: /Command Injection/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("reveals the explanation and the snippet when expanded", async () => {
    const user = userEvent.setup();
    render(<FindingCard finding={full} />);

    await user.click(screen.getByRole("button", { name: /Command Injection/ }));

    expect(screen.getByRole("button", { name: /Command Injection/ }))
      .toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Attackers could run unauthorized utilities/)).toBeInTheDocument();
    expect(screen.getByText(/Use subprocess.run/)).toBeInTheDocument();
    expect(screen.getByText(/subprocess.run\(cmd, shell=True\)/)).toBeInTheDocument();
  });

  it("renders no expand control when there is nothing to expand", () => {
    render(<FindingCard finding={{ title: "Dead import", severity: "Low" }} />);

    expect(screen.getByText("Dead import")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows a confidence of 0 rather than hiding it", () => {
    render(<FindingCard finding={{ ...full, confidence: 0 }} />);

    expect(screen.getByText("0% Match")).toBeInTheDocument();
  });
});
```

Check whether `@testing-library/user-event` is already a devDependency:

```
cd D:/ETPROJECT/frontend && node -e "const p=require('./package.json');console.log(p.devDependencies['@testing-library/user-event']||p.dependencies['@testing-library/user-event']||'ABSENT')"
```

If it prints `ABSENT`, **do not install it** — that needs asking first. Instead use `fireEvent.click` from `@testing-library/react` in place of `userEvent`, dropping the `user` setup lines.

- [ ] **Step 2: Run the test and verify it fails**

```
cd D:/ETPROJECT/frontend && npx vitest run src/components/FindingCard.test.tsx
```

Expected: FAIL — the explanation text is present while collapsed, and no button exists.

- [ ] **Step 3: Implement the collapsible card**

Replace `frontend/src/components/FindingCard.tsx` with:

```tsx
import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { SeverityBadge } from "@/components/SeverityBadge";
import { TrustBoundaryBadge } from "@/components/TrustBoundaryBadge";
import type { FindingView } from "@/lib/findings";
import { cn } from "@/lib/utils";

interface FindingCardProps {
  finding: FindingView;
  className?: string;
}

/**
 * One finding, explained the same way everywhere.
 *
 * Collapsed by default (J2/F9): a real report carries hundreds of findings and
 * rendering every explanation at once produced a wall nobody read. What stays
 * visible while closed is what you triage on — severity, what it is, which
 * file and line, trust boundary, confidence. The explanation is one click away.
 *
 * A finding with nothing to expand renders no control at all, so the list never
 * offers a button that does nothing.
 *
 * Absent fields render nothing. Numeric fields are tested against `undefined`
 * rather than truthiness, so a confidence of 0 still shows.
 */
export function FindingCard({ finding, className }: FindingCardProps) {
  const [open, setOpen] = useState(false);

  const hasDetail = Boolean(
    finding.detail || finding.whyItMatters || finding.howToFix || finding.snippet
  );

  const badges = (
    <div className="flex gap-2 mt-2 flex-wrap">
      {finding.fileName && (
        <Badge variant="outline" className="text-[10px] font-mono">{finding.fileName}</Badge>
      )}
      {finding.line !== undefined && (
        <Badge variant="outline" className="text-[10px] font-mono">Line {finding.line}</Badge>
      )}
      {finding.category && (
        <Badge variant="outline" className="text-[10px]">{finding.category}</Badge>
      )}
      <TrustBoundaryBadge trustBoundary={finding.trustBoundary} />
      {finding.confidence !== undefined && (
        <Badge variant="outline" className="text-[10px] border-primary/20 text-primary/80">
          {(finding.confidence * 100).toFixed(0)}% Match
        </Badge>
      )}
    </div>
  );

  const body = (
    <>
      {finding.detail && (
        <p className="text-sm text-muted-foreground mt-1">{finding.detail}</p>
      )}

      {finding.whyItMatters && (
        <p className="text-xs text-muted-foreground mt-1.5">
          <span className="font-medium text-foreground/80">Context:</span> {finding.whyItMatters}
        </p>
      )}

      {finding.snippet && (
        <pre className="mt-2 p-3 rounded-lg bg-background/60 border border-border overflow-x-auto text-xs font-mono leading-relaxed">
          <code>{finding.snippet}</code>
        </pre>
      )}

      {finding.howToFix && (
        <div className="mt-2 p-3 rounded-lg bg-primary/5 border border-primary/20">
          <p className="text-xs text-muted-foreground mb-1">How to fix</p>
          <p className="text-sm text-primary">{finding.howToFix}</p>
        </div>
      )}
    </>
  );

  if (!hasDetail) {
    return (
      <div className={cn("flex items-start gap-3 p-3 rounded-lg bg-secondary/20", className)}>
        <SeverityBadge severity={finding.severity} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold">{finding.title}</p>
          {badges}
        </div>
      </div>
    );
  }

  return (
    <div className={cn("flex items-start gap-3 p-3 rounded-lg bg-secondary/20", className)}>
      <SeverityBadge severity={finding.severity} />

      <div className="flex-1 min-w-0">
        <Collapsible open={open} onOpenChange={setOpen}>
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex w-full items-start gap-2 text-left rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              <span className="text-sm font-semibold flex-1">{finding.title}</span>
              <ChevronDown
                aria-hidden="true"
                className={cn(
                  "w-4 h-4 shrink-0 mt-0.5 text-muted-foreground transition-transform",
                  open && "rotate-180"
                )}
              />
            </button>
          </CollapsibleTrigger>

          <CollapsibleContent>{body}</CollapsibleContent>
        </Collapsible>

        {badges}
      </div>
    </div>
  );
}
```

**On `aria-expanded`:** Radix's `Collapsible.Trigger` supplies `aria-expanded` and `aria-controls` itself. Step 4's test asserts the attribute directly — if it turns out to be absent, add `aria-expanded={open}` explicitly to the `<button>` rather than assuming.

- [ ] **Step 4: Run the card test and verify it passes**

```
cd D:/ETPROJECT/frontend && npx vitest run src/components/FindingCard.test.tsx
```

Expected: `5 passed`.

- [ ] **Step 5: Fix the two page tests this breaks**

```
cd D:/ETPROJECT/frontend && npx vitest run src/pages/SecurityReport.test.tsx src/pages/IssueExplorer.test.tsx
```

These will fail on assertions like `expect(screen.getByText(/Attackers could run unauthorized utilities/)).toBeInTheDocument()`, because that text is now behind the collapse.

In each failing test, click the finding's trigger before asserting on explanation text:

```tsx
await userEvent.click(screen.getByRole("button", { name: /Command Injection/ }));
```

Make the enclosing `it` callback `async`. Assertions on the title, the severity badge, the file badge, the line badge and the counts need no change — those stay visible while collapsed.

If `@testing-library/user-event` was `ABSENT` in Step 1, use `fireEvent.click(...)` instead and keep the callbacks synchronous.

- [ ] **Step 6: Run the full frontend suite and typecheck**

```
cd D:/ETPROJECT/frontend && npx vitest run && npm run typecheck
```

Expected: **≥ 65 passed**, 0 failed; typecheck exit 0. Read the count.

The arithmetic, so you can tell a real regression from a miscount: baseline 59,
plus Task 3's 4 new tests in `findings.test.ts` = 63. `FindingCard.test.tsx` had
**3** tests and Step 1 replaces it with **5**, so +2 = **65**. Task 5's edits to
`SecurityReport.test.tsx` and Task 4's to `IssueExplorer.test.tsx` modify
existing tests rather than adding any.

- [ ] **Step 7: Commit**

```bash
cd D:/ETPROJECT
git add frontend/src/components/FindingCard.tsx frontend/src/components/FindingCard.test.tsx frontend/src/pages/SecurityReport.test.tsx frontend/src/pages/IssueExplorer.test.tsx
git commit -m "Collapse finding cards and show the flagged source when open

A real report carries hundreds of findings and rendering every explanation
at once produced a wall. Severity, title, file, line, trust boundary and
confidence stay visible closed; the explanation and the snippet are one
click away. Cards with nothing to expand render no control."
git status --short
```

---

### Task 5: Security Report groups by severity, with five navigating tiers

**Files:**
- Modify: `frontend/src/pages/SecurityReport.tsx`
- Modify: `frontend/src/pages/SecurityReport.test.tsx`
- Modify: `frontend/src/test/setup.ts`

**Interfaces:**
- Consumes: `FindingCard` from Task 4.
- Produces: group headings with ids `severity-critical`, `severity-high`, `severity-medium`, `severity-low`, `severity-info`, and tier buttons that scroll to them. Task 6's Playwright spec drives those buttons.

**Why five tiers and not four:** `Severity` in `lib/types.ts` has five values, and its doc comment records that `Info` exists precisely so a taint-cleared code-exec sink is not collapsed into Low. The page renders four tiles today, so an `Info` finding appears in the list while no tile counts it and the tiles do not sum to the headline. That is the same defect class as audit item F14. Corrected here.

- [ ] **Step 1: Add the two jsdom stubs the page needs**

jsdom implements neither `Element.prototype.scrollIntoView` nor `window.matchMedia`. Append to `frontend/src/test/setup.ts`:

```ts
import { vi } from "vitest";

// jsdom implements neither of these, and SecurityReport's tier navigation
// calls both. Stubbed globally so no individual test has to remember.
Element.prototype.scrollIntoView = vi.fn();

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});
```

- [ ] **Step 2: Write the failing test**

Append to `frontend/src/pages/SecurityReport.test.tsx`:

```tsx
  it("groups findings by severity and omits groups with nothing in them", () => {
    mockUseScan.mockReturnValue({
      currentReport: reportWith([
        {
          name: "runner.py",
          path: "backend/app/runner.py",
          fileType: "production",
          security: [
            { type: "Command Injection", severity: "Critical", description: "d", file: "runner.py", line: 1 },
            { type: "Weak Hash", severity: "Low", description: "d", file: "runner.py", line: 2 },
            { type: "Local Exec", severity: "Info", description: "d", file: "runner.py", line: 3 },
          ],
        },
      ]),
    });

    render(<SecurityReport />);

    expect(screen.getByRole("heading", { name: /Critical/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Low/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Info/ })).toBeInTheDocument();
    // Nothing is High or Medium here, so neither heading exists.
    expect(screen.queryByRole("heading", { name: /High/ })).toBeNull();
    expect(screen.queryByRole("heading", { name: /Medium/ })).toBeNull();
  });

  it("counts Info findings on a tier, so the tiers sum to the headline", () => {
    mockUseScan.mockReturnValue({
      currentReport: reportWith([
        {
          name: "runner.py",
          path: "backend/app/runner.py",
          fileType: "production",
          security: [
            { type: "Local Exec", severity: "Info", description: "d", file: "runner.py", line: 3 },
          ],
        },
      ]),
    });

    render(<SecurityReport />);

    const tier = screen.getByRole("button", { name: /1 Info/ });
    expect(tier).toBeInTheDocument();
  });

  it("scrolls to a group when its tier is activated", async () => {
    mockUseScan.mockReturnValue({
      currentReport: reportWith([
        {
          name: "runner.py",
          path: "backend/app/runner.py",
          fileType: "production",
          security: [
            { type: "Command Injection", severity: "Critical", description: "d", file: "runner.py", line: 1 },
          ],
        },
      ]),
    });

    render(<SecurityReport />);

    await userEvent.click(screen.getByRole("button", { name: /1 Critical/ }));

    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it("renders a zero tier as text, not a control", () => {
    mockUseScan.mockReturnValue({
      currentReport: reportWith([
        {
          name: "runner.py",
          path: "backend/app/runner.py",
          fileType: "production",
          security: [
            { type: "Command Injection", severity: "Critical", description: "d", file: "runner.py", line: 1 },
          ],
        },
      ]),
    });

    render(<SecurityReport />);

    // Four tiers are empty; none of them is a button.
    expect(screen.queryByRole("button", { name: /0 High/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /0 Info/ })).toBeNull();
  });
```

Add `import userEvent from "@testing-library/user-event";` at the top (or use `fireEvent` per Task 4 Step 1 if it is absent).

- [ ] **Step 3: Run the test and verify it fails**

```
cd D:/ETPROJECT/frontend && npx vitest run src/pages/SecurityReport.test.tsx
```

Expected: FAIL — no headings exist, and the tiles are `Card`s, not buttons.

- [ ] **Step 4: Implement**

In `frontend/src/pages/SecurityReport.tsx`, add to the imports:

```tsx
import type { Severity } from "@/lib/types";
```

Replace the block that computes `criticalCount` / `highCount` with:

```tsx
  // Five, not four. `Severity` has five values and `types.ts` records why Info
  // is distinct: a code-exec sink that taint proved is reachable only from
  // local operator input. The page used to render four tiles, so an Info
  // finding showed in the list below while no tile counted it and the tiles
  // did not sum to the headline.
  const SEVERITY_ORDER: Severity[] = ["Critical", "High", "Medium", "Low", "Info"];

  const groups = SEVERITY_ORDER.map((severity) => ({
    severity,
    id: `severity-${severity.toLowerCase()}`,
    findings: allVulnerabilities.filter((v) => v.severity === severity),
  }));

  // Scrolling alone moves the viewport and leaves a keyboard or screen-reader
  // user where they were. Moving focus is what makes a tier a navigation
  // control rather than a decoration.
  const jumpTo = (id: string) => {
    const target = document.getElementById(id);
    if (!target) return;

    const reduced =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    target.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
    target.focus();
  };

  const TIER_STYLES: Record<Severity, { border: string; text: string }> = {
    Critical: { border: "border-destructive/30", text: "text-destructive" },
    High: { border: "border-destructive/20", text: "text-destructive/80" },
    Medium: { border: "border-warning/20", text: "text-warning" },
    Low: { border: "border-info/20", text: "text-info" },
    Info: { border: "border-border", text: "text-muted-foreground" },
  };
```

Replace the entire four-`Card` tile grid with:

```tsx
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {groups.map(({ severity, id, findings }) => {
          const styles = TIER_STYLES[severity];
          const inner = (
            <>
              <p className={cn("text-3xl font-bold font-mono", styles.text)}>{findings.length}</p>
              <p className="text-xs text-muted-foreground mt-1">{severity}</p>
            </>
          );

          // A tier with nothing behind it is not a control: activating it
          // would jump to a group that renders nothing.
          if (findings.length === 0) {
            return (
              <Card key={severity} className={cn("bg-card", styles.border)}>
                <CardContent className="pt-6 text-center">{inner}</CardContent>
              </Card>
            );
          }

          return (
            <Card key={severity} className={cn("bg-card", styles.border)}>
              <CardContent className="p-0">
                <button
                  type="button"
                  onClick={() => jumpTo(id)}
                  aria-label={`${findings.length} ${severity} — jump to findings`}
                  className="w-full pt-6 pb-6 px-6 text-center rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background hover:bg-secondary/20 transition-colors"
                >
                  {inner}
                </button>
              </CardContent>
            </Card>
          );
        })}
      </div>
```

Replace the flat findings list (`allVulnerabilities.map(...)`) with the grouped
one. The empty-state branch is reproduced in full below — including its comment,
which explains why the copy is scoped to production files — so paste this whole
block rather than reconstructing it:

```tsx
      <div className="space-y-8">
        {allVulnerabilities.length === 0 ? (
          <Card className="bg-card border-primary/30">
            <CardContent className="pt-6 text-center">
              <Shield className="w-12 h-12 text-primary mx-auto mb-2" />
              {/* Scoped to match the headline above. An unqualified "none detected"
                  would contradict the "N further findings in test/non-code files"
                  line this same page renders when excludedCount > 0. */}
              <p className="text-primary font-medium">No security findings in production files</p>
            </CardContent>
          </Card>
        ) : (
          groups
            .filter((g) => g.findings.length > 0)
            .map(({ severity, id, findings }) => (
              <section key={severity} className="space-y-4">
                <h2
                  id={id}
                  tabIndex={-1}
                  className="text-lg font-semibold tracking-tight scroll-mt-24 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
                >
                  {severity} — {findings.length} finding{findings.length === 1 ? "" : "s"}
                </h2>
                {findings.map((vuln, i) => (
                  <FindingCard key={`${severity}-${i}`} finding={fromSecurityVulnerability(vuln)} />
                ))}
              </section>
            ))
        )}
      </div>
```

Keep the real empty-state `Card` in the `allVulnerabilities.length === 0` branch — the `null` above is shorthand for "do not touch that branch", not something to paste.

Add `import { cn } from "@/lib/utils";` if it is not already imported.

- [ ] **Step 5: Run the test and verify it passes**

```
cd D:/ETPROJECT/frontend && npx vitest run src/pages/SecurityReport.test.tsx
```

Expected: all pass, including the pre-existing tests in that file.

- [ ] **Step 6: Full suite, typecheck, build**

```
cd D:/ETPROJECT/frontend && npx vitest run && npm run typecheck && npm run build
```

Expected: **≥ 69 passed** (65 from Task 4, plus this task's 4 new tests),
typecheck exit 0, build succeeds. Read the counts.

- [ ] **Step 7: Commit**

```bash
cd D:/ETPROJECT
git add frontend/src/pages/SecurityReport.tsx frontend/src/pages/SecurityReport.test.tsx frontend/src/test/setup.ts
git commit -m "Group security findings by severity and make the tiers navigate

The tiles counted findings and offered no way to reach them, and the list
below was flat and in file order. They are now five tiles, not four: Severity
has five values and an Info finding previously showed in the list while no
tile counted it, so the tiles did not sum to the headline.

Activating a tier moves focus to its group heading, not just the viewport."
git status --short
```

---

### Task 6: Keyboard path, end to end

**Files:**
- Create: `frontend/e2e/findings.spec.ts`

**Interfaces:**
- Consumes: the trigger button from Task 4 and the tier buttons from Task 5.
- Produces: nothing other tasks depend on. This is the phase's acceptance evidence for F16.

**Context you need:** `frontend/e2e/fixtures.ts` exports `mockBackend(page)`, `loadDemo(page)` and `navigateTo(page, path)`. `page.goto()` wipes the scan — `ScanContext` holds the report in plain `useState` with no persistence — so navigate by clicking the sidebar via `navigateTo`, never `goto`. The demo report is `frontend/src/lib/mock-data.ts`.

- [ ] **Step 1: Write the spec**

Create `frontend/e2e/findings.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { loadDemo, mockBackend, navigateTo } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
});

/**
 * F16. The tiles and the finding cards are new interactive elements, and a
 * control that only works with a mouse is not a control. These drive both
 * from the keyboard alone.
 */

test("a finding card expands from the keyboard", async ({ page }) => {
  await loadDemo(page);
  await navigateTo(page, "/security");

  const trigger = page.getByRole("button", { expanded: false }).first();
  await expect(trigger).toBeVisible();

  await trigger.focus();
  await page.keyboard.press("Enter");

  await expect(trigger).toHaveAttribute("aria-expanded", "true");
});

test("a severity tier moves focus to its group heading", async ({ page }) => {
  await loadDemo(page);
  await navigateTo(page, "/security");

  // Whichever tier the demo data actually populates. Matching on the aria-label
  // shape rather than a hardcoded severity keeps this from breaking when the
  // demo report changes.
  const tier = page.getByRole("button", { name: /jump to findings/ }).first();
  await expect(tier).toBeVisible();

  const label = await tier.getAttribute("aria-label");
  const severity = label!.split(" ")[1];

  await tier.focus();
  await page.keyboard.press("Enter");

  const heading = page.getByRole("heading", { name: new RegExp(`^${severity} — `) });
  await expect(heading).toBeFocused();
});
```

- [ ] **Step 2: Run it and read the result**

```
cd D:/ETPROJECT/frontend && npx playwright test findings.spec.ts
```

If the demo report in `src/lib/mock-data.ts` yields no security findings on production files, the Security Report page shows its empty state and both tests fail on `toBeVisible`. In that case, read `mock-data.ts` and confirm which file entries have `fileType: "production"` with a non-empty `security` array — `SecurityReport.tsx` filters to production files only. Adjust the demo data only if it genuinely has no production security finding; otherwise fix the selector.

- [ ] **Step 3: Run the whole Playwright suite**

```
cd D:/ETPROJECT/frontend && npx playwright test
```

Expected: **≥ 19 passed** (17 baseline + 2), 0 failed. Read the count. Note the suite runs three projects (desktop, tablet-768, mobile-375), so these two specs contribute more than two results.

- [ ] **Step 4: Commit**

```bash
cd D:/ETPROJECT
git add frontend/e2e/findings.spec.ts
git commit -m "Drive the new finding controls from the keyboard in e2e

F16. Covers the two interactive elements J2 adds: the card expand trigger
and the severity tiers. The tier test asserts focus lands on the heading,
because scrolling alone leaves a keyboard user where they were."
git status --short
```

---

## Final acceptance

Run all of it, from a clean tree, and record the counts. **Prior notes are testimony; only output from this run is evidence.**

```bash
cd D:/ETPROJECT && venv\Scripts\python.exe -m pytest backend/tests -q
cd D:/ETPROJECT/frontend && npx vitest run
cd D:/ETPROJECT/frontend && npm run typecheck
cd D:/ETPROJECT/frontend && npm run build
cd D:/ETPROJECT/frontend && npx playwright test
```

| Criterion | Floor |
|---|---|
| pytest | ≥ 429 passed, 0 failed |
| vitest | ≥ 69 passed, 0 failed |
| `npm run typecheck` (`tsc -b`) | exit 0 |
| `npm run build` | succeeds |
| Playwright | ≥ 19 passed, 0 failed |

**Plus the one that actually matters.** Scan a real repository and confirm the security findings carry real source:

```bash
cd D:/ETPROJECT && venv\Scripts\python.exe -m pytest backend/tests/test_snippet_wiring.py -q
```

and then, against a freshly produced scan (not a cached one — the 523 files in `backend/app/.cache/` all predate Task 2), confirm at least one finding's `snippet` starts with a line number and contains code.

Finally, update `docs/HANDOVER.md` §1 and §3, and append to `docs/DECISIONS.md`: the five-tier correction, and the decision to make `snippet` real rather than render the placeholder. Note which model made them.

`docs/HANDOVER.md` §1 currently states `main` is 16 commits ahead of `origin/main` and that CI has not run. Both were false as of this session — `main` equalled `origin/main` at `e857e0e` with CI run `32357489001` green. Correct that line too.
