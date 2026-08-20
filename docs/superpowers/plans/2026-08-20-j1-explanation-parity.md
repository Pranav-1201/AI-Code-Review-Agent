# J1 — Explanation Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every finding explain itself the same way on every page, using data the backend already computes.

**Architecture:** `FileAnalysis.tsx:266-281` already renders `why_it_matters`, `how_to_fix` and `confidence` correctly; `SecurityReport` and `IssueExplorer` never read them. Extract that treatment into a pure normalizer (`lib/findings.ts`) plus a presentational component (`components/FindingCard.tsx`), then adopt it on the pages that lack it. Frontend only — no backend change, no LLM, no new dependency.

**Tech Stack:** React 18 + TypeScript, Vite 5.4.21, Tailwind, shadcn/ui, vitest 3.2 + jsdom + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-08-20-j1-explanation-parity-design.md` (commit `bac4238`)

## Global Constraints

- **Interpreter for backend work:** `venv\Scripts\python.exe` at the repo root. This plan needs none — it is frontend-only.
- **Run all frontend commands from `frontend/`.** `npx vite` from the repo root resolves a different Vite major than the pinned 5.4.21.
- **Typecheck is `npm run typecheck` (`tsc -b`). Never `tsc --noEmit`** — `frontend/tsconfig.json` is solution-style (`"files": []` plus `references`), so `--noEmit` compiles an empty program and exits 0 having checked nothing (DECISIONS D16).
- **Test command:** `npx vitest run` from `frontend/`. Config lives in `frontend/vite.config.ts:38-46`; tests are collected from `src/**/*.test.{ts,tsx}` only, so Playwright specs under `e2e/` stay out.
- **No new runtime dependency** (CONSTRAINTS 7). Everything this plan needs is already installed.
- **`git add -A` is banned** (CONSTRAINTS 2). Stage explicit paths, always.
- **Run `git status --short` after every commit** and delete any zero-byte junk file that appears. Use quoted `rm` for names containing parens or brackets.
- **No AI attribution in any commit message** (CONSTRAINTS 1).
- **One logical change per commit** (CONSTRAINTS 9).
- **Every optional field renders nothing when absent** — no empty label, no "N/A", no placeholder dash.
- Existing baseline, measured 2026-08-20 in 40.94s: **42 tests passing across 6 files**. Every count below is derived from it.

---

## File Structure

| File | Responsibility |
|---|---|
| `frontend/src/lib/findings.ts` | **Create.** Pure transforms from the two backend finding shapes to one view-model. No React import. |
| `frontend/src/lib/findings.test.ts` | **Create.** Normalizer behaviour, including field-absence. |
| `frontend/src/components/FindingCard.tsx` | **Create.** Presentational card for one `FindingView`. Knows nothing about scans. |
| `frontend/src/components/FindingCard.test.tsx` | **Create.** Render-when-present, render-nothing-when-absent. |
| `frontend/src/pages/SecurityReport.tsx` | **Modify.** Adopt the card (Task 3); scope to production files (Task 6). |
| `frontend/src/pages/SecurityReport.test.tsx` | **Create.** First page-level test in the repo. |
| `frontend/src/pages/IssueExplorer.tsx` | **Modify.** Adopt the card. |
| `frontend/src/pages/AISuggestions.tsx` | **Modify.** Markdown rendering + provenance badge. |
| `frontend/src/pages/ScanResults.tsx` | **Modify.** Relabel the security tile. |
| `frontend/src/pages/FileAnalysis.tsx` | **Modify, last.** Swap the inline block for the card. |

---

### Task 1: The finding view-model and its normalizers

**Files:**
- Create: `frontend/src/lib/findings.ts`
- Test: `frontend/src/lib/findings.test.ts`

**Interfaces:**
- Consumes: `Severity`, `FileIssue`, `SecurityVulnerability`, `FileAnalysis` from `frontend/src/lib/types.ts`.
- Produces: `FindingView` (interface), `fromSecurityVulnerability(v: SecurityVulnerability): FindingView`, `fromFileIssue(i: FileIssue, file: FileAnalysis): FindingView`. Tasks 2–7 all depend on these exact names.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/findings.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { fromFileIssue, fromSecurityVulnerability } from "./findings";
import type { FileAnalysis, FileIssue, SecurityVulnerability } from "./types";

const vuln: SecurityVulnerability = {
  type: "Command Injection",
  severity: "Critical",
  description: "subprocess call with a non-constant argv[0]",
  file: "backend/app/runner.py",
  line: 42,
  recommendation: "Pass a list, not a shell string.",
  why_it_matters: "Running external commands with untrusted input can let attackers run unauthorized utilities on the server.",
  how_to_fix: "Use subprocess.run([...]) with shell=False.",
  confidence: 0.9,
  trust_boundary: "untrusted_input",
};

const issue: FileIssue = {
  message: "Function exceeds the complexity budget",
  severity: "Medium",
  category: "maintainability",
  line: 7,
  why_it_matters: "Complex functions are harder to test and change safely.",
  how_to_fix: "Extract the branching into helper functions.",
  confidence: 0.5,
};

const file = { name: "runner.py", path: "backend/app/runner.py" } as FileAnalysis;

describe("fromSecurityVulnerability", () => {
  it("carries the explanation fields the pages need", () => {
    const view = fromSecurityVulnerability(vuln);

    expect(view.title).toBe("Command Injection");
    expect(view.detail).toBe("subprocess call with a non-constant argv[0]");
    expect(view.severity).toBe("Critical");
    expect(view.category).toBe("security");
    expect(view.whyItMatters).toBe(vuln.why_it_matters);
    expect(view.confidence).toBe(0.9);
    expect(view.trustBoundary).toBe("untrusted_input");
  });

  it("prefers how_to_fix over the older recommendation field", () => {
    expect(fromSecurityVulnerability(vuln).howToFix).toBe("Use subprocess.run([...]) with shell=False.");
  });

  it("falls back to recommendation when how_to_fix is absent", () => {
    const { how_to_fix, ...withoutFix } = vuln;

    expect(fromSecurityVulnerability(withoutFix).howToFix).toBe("Pass a list, not a shell string.");
  });

  it("leaves absent fields undefined rather than inventing empty strings", () => {
    const bare: SecurityVulnerability = {
      type: "Weak Hash",
      severity: "Low",
      description: "md5 used for a digest",
      file: "util.py",
    };
    const view = fromSecurityVulnerability(bare);

    expect(view.whyItMatters).toBeUndefined();
    expect(view.howToFix).toBeUndefined();
    expect(view.confidence).toBeUndefined();
    expect(view.trustBoundary).toBeUndefined();
    expect(view.line).toBeUndefined();
  });

  it("shortens the file path to a basename for display but keeps the full path", () => {
    const view = fromSecurityVulnerability(vuln);

    expect(view.fileName).toBe("runner.py");
    expect(view.filePath).toBe("backend/app/runner.py");
  });
});

describe("fromFileIssue", () => {
  it("uses the message as the title and the issue's own category", () => {
    const view = fromFileIssue(issue, file);

    expect(view.title).toBe("Function exceeds the complexity budget");
    expect(view.detail).toBeUndefined();
    expect(view.category).toBe("maintainability");
    expect(view.fileName).toBe("runner.py");
    expect(view.filePath).toBe("backend/app/runner.py");
    expect(view.whyItMatters).toBe(issue.why_it_matters);
    expect(view.howToFix).toBe("Extract the branching into helper functions.");
  });

  it("leaves absent fields undefined", () => {
    const bare: FileIssue = { message: "Unused import", severity: "Low", category: "style" };
    const view = fromFileIssue(bare, file);

    expect(view.whyItMatters).toBeUndefined();
    expect(view.howToFix).toBeUndefined();
    expect(view.confidence).toBeUndefined();
    expect(view.line).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run the test and watch it fail**

```bash
cd frontend && npx vitest run src/lib/findings.test.ts
```

Expected: FAIL — `Failed to resolve import "./findings"`. A test that has never been seen red proves nothing.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/lib/findings.ts`:

```ts
import type { FileAnalysis, FileIssue, SecurityVulnerability, Severity } from "./types";

/**
 * One finding, normalized for display.
 *
 * The backend produces two differently-shaped finding objects — security
 * vulnerabilities and file issues — that a reader experiences as the same kind
 * of thing. This is the shape the UI renders, so `FindingCard` never has to
 * know which of the two it was handed.
 *
 * Every field beyond title and severity is optional and absent means absent:
 * consumers render nothing at all rather than an empty label.
 */
export interface FindingView {
  title: string;
  detail?: string;
  severity: Severity;
  category?: string;
  fileName?: string;
  filePath?: string;
  line?: number;
  whyItMatters?: string;
  howToFix?: string;
  confidence?: number;
  trustBoundary?: string;
}

export function fromSecurityVulnerability(v: SecurityVulnerability): FindingView {
  return {
    title: v.type,
    detail: v.description,
    severity: v.severity,
    category: "security",
    fileName: v.file ? v.file.split("/").pop() || v.file : undefined,
    filePath: v.file,
    line: v.line,
    whyItMatters: v.why_it_matters,
    // `recommendation` predates `how_to_fix`; reports in the wild carry either.
    howToFix: v.how_to_fix ?? v.recommendation,
    confidence: v.confidence,
    trustBoundary: v.trust_boundary,
  };
}

export function fromFileIssue(i: FileIssue, file: FileAnalysis): FindingView {
  return {
    title: i.message,
    severity: i.severity,
    category: i.category,
    fileName: file.name,
    filePath: file.path,
    line: i.line,
    whyItMatters: i.why_it_matters,
    howToFix: i.how_to_fix,
    confidence: i.confidence,
    trustBoundary: i.trust_boundary,
  };
}
```

- [ ] **Step 4: Run the test and the typecheck**

```bash
cd frontend && npx vitest run src/lib/findings.test.ts && npm run typecheck
```

Expected: 7 tests pass, suite total 49 across 7 files; typecheck exits 0. If `npm run typecheck` prints no file count, do not treat it as evidence — confirm it is running `tsc -b` from `package.json:13`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/findings.ts frontend/src/lib/findings.test.ts
git commit -m "Normalize both finding shapes into one view-model"
git status --short
```

---

### Task 2: The FindingCard component

**Files:**
- Create: `frontend/src/components/FindingCard.tsx`
- Test: `frontend/src/components/FindingCard.test.tsx`

**Interfaces:**
- Consumes: `FindingView` from Task 1; `SeverityBadge` (`components/SeverityBadge.tsx`, prop `severity: Severity`); `TrustBoundaryBadge` (`components/TrustBoundaryBadge.tsx`, prop `trustBoundary?: string`, returns `null` for undefined or unknown values); `Badge` from `components/ui/badge`; `cn` from `lib/utils`.
- Produces: `FindingCard({ finding, className }: { finding: FindingView; className?: string })`. Tasks 3, 4 and 7 render it.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/FindingCard.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
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
  confidence: 0.9,
  trustBoundary: "untrusted_input",
};

describe("FindingCard", () => {
  it("shows why a finding matters and how to fix it", () => {
    render(<FindingCard finding={full} />);

    expect(screen.getByText("Command Injection")).toBeInTheDocument();
    expect(screen.getByText(/Attackers could run unauthorized utilities/)).toBeInTheDocument();
    expect(screen.getByText(/Use subprocess.run/)).toBeInTheDocument();
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("Untrusted input")).toBeInTheDocument();
    expect(screen.getByText("90% Match")).toBeInTheDocument();
    expect(screen.getByText("Line 42")).toBeInTheDocument();
  });

  it("renders no label at all for fields the analyzer did not produce", () => {
    const bare: FindingView = { title: "Unused import", severity: "Low" };

    render(<FindingCard finding={bare} />);

    expect(screen.getByText("Unused import")).toBeInTheDocument();
    // The failure this pins: a bare "Context:" or "How to fix" heading with
    // nothing beside it reads as a broken analyzer, not an absent field.
    expect(screen.queryByText(/Context:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/How to fix/)).not.toBeInTheDocument();
    expect(screen.queryByText(/% Match/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Line /)).not.toBeInTheDocument();
  });

  it("renders a zero confidence rather than swallowing it as falsy", () => {
    render(<FindingCard finding={{ title: "Guess", severity: "Info", confidence: 0 }} />);

    expect(screen.getByText("0% Match")).toBeInTheDocument();
  });
});
```

The third test is deliberate: the inline block on `FileAnalysis.tsx:281` guards with `issue.confidence &&`, so a confidence of exactly 0 renders nothing. The extracted card fixes that.

- [ ] **Step 2: Run the test and watch it fail**

```bash
cd frontend && npx vitest run src/components/FindingCard.test.tsx
```

Expected: FAIL — `Failed to resolve import "./FindingCard"`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/FindingCard.tsx`:

```tsx
import { Badge } from "@/components/ui/badge";
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
 * The layout is lifted from the inline block that FileAnalysis has always used,
 * combined with the highlighted fix box SecurityReport used for its
 * `recommendation` — so adopting this loses nothing either page rendered before.
 *
 * Absent fields render nothing. Numeric fields are tested against `undefined`
 * rather than truthiness, so a confidence of 0 still shows.
 */
export function FindingCard({ finding, className }: FindingCardProps) {
  return (
    <div className={cn("flex items-start gap-3 p-3 rounded-lg bg-secondary/20", className)}>
      <SeverityBadge severity={finding.severity} />

      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold">{finding.title}</p>

        {finding.detail && (
          <p className="text-sm text-muted-foreground mt-1">{finding.detail}</p>
        )}

        {finding.whyItMatters && (
          <p className="text-xs text-muted-foreground mt-1.5">
            <span className="font-medium text-foreground/80">Context:</span> {finding.whyItMatters}
          </p>
        )}

        {finding.howToFix && (
          <div className="mt-2 p-3 rounded-lg bg-primary/5 border border-primary/20">
            <p className="text-xs text-muted-foreground mb-1">How to fix</p>
            <p className="text-sm text-primary">{finding.howToFix}</p>
          </div>
        )}

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
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests and the typecheck**

```bash
cd frontend && npx vitest run src/components/FindingCard.test.tsx && npm run typecheck
```

Expected: 3 tests pass; typecheck exits 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/FindingCard.tsx frontend/src/components/FindingCard.test.tsx
git commit -m "Give every finding one way to explain itself"
git status --short
```

---

### Task 3: SecurityReport adopts the card (F7)

**Files:**
- Modify: `frontend/src/pages/SecurityReport.tsx:63-88` (the `allVulnerabilities.map` block)
- Test: `frontend/src/pages/SecurityReport.test.tsx` (create)

**Interfaces:**
- Consumes: `FindingCard` (Task 2), `fromSecurityVulnerability` (Task 1), `useScan` from `@/context/ScanContext`.
- Produces: nothing new. The severity tile counts and the empty state are unchanged by this task.

`ScanProvider` calls `listScans()` on mount, so page tests mock the context hook instead of wrapping in the real provider.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/SecurityReport.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ScanReport } from "@/lib/types";

const mockUseScan = vi.fn();
vi.mock("@/context/ScanContext", () => ({ useScan: () => mockUseScan() }));

import SecurityReport from "./SecurityReport";

function reportWith(files: Partial<ScanReport["files"][number]>[]): ScanReport {
  return { files } as ScanReport;
}

describe("SecurityReport", () => {
  it("explains why each finding matters and how to fix it", () => {
    mockUseScan.mockReturnValue({
      currentReport: reportWith([
        {
          name: "runner.py",
          path: "backend/app/runner.py",
          fileType: "production",
          security: [
            {
              type: "Command Injection",
              severity: "Critical",
              description: "subprocess call with a non-constant argv[0]",
              file: "backend/app/runner.py",
              line: 42,
              why_it_matters: "Attackers could run unauthorized utilities on the server.",
              how_to_fix: "Use subprocess.run([...]) with shell=False.",
              confidence: 0.9,
              trust_boundary: "untrusted_input",
            },
          ],
        },
      ]),
    });

    render(<SecurityReport />);

    expect(screen.getByText("Command Injection")).toBeInTheDocument();
    // These three are computed by the backend today and rendered by no page.
    expect(screen.getByText(/Attackers could run unauthorized utilities/)).toBeInTheDocument();
    expect(screen.getByText(/Use subprocess.run/)).toBeInTheDocument();
    expect(screen.getByText("90% Match")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test and watch it fail**

```bash
cd frontend && npx vitest run src/pages/SecurityReport.test.tsx
```

Expected: FAIL — the "why it matters", "how to fix" and confidence assertions cannot find their text, because the page renders `description` and `recommendation` only.

- [ ] **Step 3: Rewrite the finding list**

In `frontend/src/pages/SecurityReport.tsx`, add to the imports:

```tsx
import { FindingCard } from "@/components/FindingCard";
import { fromSecurityVulnerability } from "@/lib/findings";
```

Replace the entire `allVulnerabilities.map((vuln, i) => (...))` expression — the `<Card>` through its closing tag — with:

```tsx
allVulnerabilities.map((vuln, i) => (
  <FindingCard key={i} finding={fromSecurityVulnerability(vuln)} />
))
```

Remove the now-unused `SeverityBadge`, `TrustBoundaryBadge` and `AlertTriangle` imports **only if** nothing else in the file still references them. `Shield` is still used by the empty state and the no-findings card; leave it.

- [ ] **Step 4: Run the full suite and the typecheck**

```bash
cd frontend && npx vitest run && npm run typecheck
```

Expected: the new test passes and the previous 52 still do — 53 total across 9 files. Typecheck exits 0 with no unused-import errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SecurityReport.tsx frontend/src/pages/SecurityReport.test.tsx
git commit -m "Say why each security finding matters and how to fix it"
git status --short
```

---

### Task 4: IssueExplorer adopts the card (F9 detail)

**Files:**
- Modify: `frontend/src/pages/IssueExplorer.tsx:84-102` (the `filteredIssues.map` block)
- Test: create `frontend/src/pages/IssueExplorer.test.tsx`

**Interfaces:**
- Consumes: `FindingCard` (Task 2), `fromFileIssue` (Task 1).
- Produces: nothing new. Search, severity and category filtering are untouched.

`IssueExplorer` currently flattens issues into `{ ...issue, fileName, filePath }`. `fromFileIssue` takes the issue and its file instead, so the flatten changes shape.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/IssueExplorer.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ScanReport } from "@/lib/types";

const mockUseScan = vi.fn();
vi.mock("@/context/ScanContext", () => ({ useScan: () => mockUseScan() }));

import IssueExplorer from "./IssueExplorer";

describe("IssueExplorer", () => {
  it("gives each issue its context and remediation, not just a message", () => {
    mockUseScan.mockReturnValue({
      currentReport: {
        files: [
          {
            name: "runner.py",
            path: "backend/app/runner.py",
            fileType: "production",
            security: [],
            issues: [
              {
                message: "Function exceeds the complexity budget",
                severity: "Medium",
                category: "maintainability",
                line: 7,
                why_it_matters: "Complex functions are harder to test and change safely.",
                how_to_fix: "Extract the branching into helper functions.",
              },
            ],
          },
        ],
      } as unknown as ScanReport,
    });

    render(<IssueExplorer />);

    expect(screen.getByText("Function exceeds the complexity budget")).toBeInTheDocument();
    expect(screen.getByText(/Complex functions are harder to test/)).toBeInTheDocument();
    expect(screen.getByText(/Extract the branching/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test and watch it fail**

```bash
cd frontend && npx vitest run src/pages/IssueExplorer.test.tsx
```

Expected: FAIL — the context and remediation assertions find nothing.

- [ ] **Step 3: Rewrite the flatten and the list**

In `frontend/src/pages/IssueExplorer.tsx`, add to the imports:

```tsx
import { FindingCard } from "@/components/FindingCard";
import { fromFileIssue } from "@/lib/findings";
```

Replace the `allIssues` flatten with one that keeps the view and the raw fields the filters need:

```tsx
const allIssues = currentReport.files.flatMap((f) =>
  f.issues.map((issue) => ({
    view: fromFileIssue(issue, f),
    severity: issue.severity,
    category: issue.category,
    message: issue.message,
    fileName: f.name,
  }))
);
```

The filter predicate keeps working unchanged — it reads `message`, `fileName`, `severity` and `category`, all still present.

Replace the `filteredIssues.map((issue, i) => (...))` expression — the `<Card>` through its closing tag — with:

```tsx
filteredIssues.map((issue, i) => (
  <FindingCard key={i} finding={issue.view} />
))
```

Remove the now-unused `Card`, `CardContent`, `SeverityBadge`, `TrustBoundaryBadge` and `Badge` imports **only if** nothing else in the file still references them. `Input`, `Select*` and `Search` are still used by the filter bar.

- [ ] **Step 4: Run the full suite and the typecheck**

```bash
cd frontend && npx vitest run && npm run typecheck
```

Expected: 54 tests across 10 files, all passing. Typecheck exits 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/IssueExplorer.tsx frontend/src/pages/IssueExplorer.test.tsx
git commit -m "Give explored issues their context and remediation"
git status --short
```

---

### Task 5: AISuggestions renders its explanation properly (F8)

**Files:**
- Modify: `frontend/src/pages/AISuggestions.tsx:33-42` (the explanation block)
- Test: `frontend/src/pages/AISuggestions.test.tsx` (create)

**Interfaces:**
- Consumes: `ReactMarkdown` from `react-markdown` and `rehypeSanitize` from `rehype-sanitize` — both already dependencies (`frontend/package.json:59,63`), already used this way at `FileAnalysis.tsx:255-259`. `ExplanationSourceBadge` from `@/components/ExplanationSourceBadge` (prop `source?: string`; renders `null` for anything other than `"llm"` or `"deterministic"`).
- Produces: nothing new.

The bug: `heuristic_refactor_engine.py:278-280` appends `**Suggested improvements (unapplied):** …` into the plain-text `explanation`, and `AISuggestions.tsx:40` renders it in a bare `<p>`, so the asterisks appear on screen.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/AISuggestions.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ScanReport } from "@/lib/types";

const mockUseScan = vi.fn();
vi.mock("@/context/ScanContext", () => ({ useScan: () => mockUseScan() }));

import AISuggestions from "./AISuggestions";

describe("AISuggestions", () => {
  it("renders the explanation as markdown instead of printing its asterisks", () => {
    mockUseScan.mockReturnValue({
      currentReport: {
        files: [
          {
            name: "runner.py",
            path: "backend/app/runner.py",
            explanation: "Reads a config file.\n\n**Suggested improvements (unapplied):** Added docstrings to 2 function(s).",
            explanationSource: "deterministic",
            suggestions: [],
          },
        ],
      } as unknown as ScanReport,
    });

    render(<AISuggestions />);

    expect(screen.getByText("Suggested improvements (unapplied):")).toBeInTheDocument();
    expect(screen.queryByText(/\*\*Suggested improvements/)).not.toBeInTheDocument();
  });

  it("labels whether the prose was written by rules or by the LLM layer", () => {
    mockUseScan.mockReturnValue({
      currentReport: {
        files: [
          { name: "a.py", path: "a.py", explanation: "Parses argv.", explanationSource: "deterministic", suggestions: [] },
        ],
      } as unknown as ScanReport,
    });

    render(<AISuggestions />);

    expect(screen.getByText("Rule-based")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test and watch it fail**

```bash
cd frontend && npx vitest run src/pages/AISuggestions.test.tsx
```

Expected: FAIL on both — the bold text is not a separate element because the markdown is never parsed, and no badge is rendered.

- [ ] **Step 3: Render markdown and label the source**

In `frontend/src/pages/AISuggestions.tsx`, add to the imports:

```tsx
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import { ExplanationSourceBadge } from "@/components/ExplanationSourceBadge";
```

Replace the explanation block — from `<div className="flex items-center gap-2 mb-2">` through the `<p>` that renders `{file.explanation}` — with:

```tsx
<div className="flex items-center gap-2 mb-2">
  <Brain className="w-4 h-4 text-accent" />
  <span className="text-sm font-semibold text-accent">AI Analysis</span>
  <ExplanationSourceBadge source={file.explanationSource} />
</div>
<div className="prose prose-sm prose-invert max-w-none text-sm text-foreground/80 prose-p:leading-relaxed">
  <ReactMarkdown rehypePlugins={[rehypeSanitize]}>{file.explanation}</ReactMarkdown>
</div>
```

The `prose` classes match `FileAnalysis.tsx:254` so both pages render this field identically.

- [ ] **Step 4: Run the full suite and the typecheck**

```bash
cd frontend && npx vitest run && npm run typecheck
```

Expected: 56 tests across 11 files, all passing. Typecheck exits 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AISuggestions.tsx frontend/src/pages/AISuggestions.test.tsx
git commit -m "Render the analysis prose instead of printing its markup"
git status --short
```

---

### Task 6: One security count, one meaning (F15)

**Files:**
- Modify: `frontend/src/pages/SecurityReport.tsx:17` and the header/tiles above the list
- Modify: `frontend/src/pages/ScanResults.tsx:80` and `:105`
- Test: extend `frontend/src/pages/SecurityReport.test.tsx` from Task 3

**Interfaces:**
- Consumes: `FileAnalysis.fileType` — `"production" | "test" | "non_code"`, already on the type at `types.ts:71`.
- Produces: nothing new.

**Do not touch the backend.** The production-only filter at `repository_review_engine.py:512-514` stays, because `total_security_issues` feeds `health_score` at 25% weight (`:570`, `:574`) and S9 — fixture exclusion — is still unstarted, so widening the count would pull this repo's own deliberately-vulnerable `backend/benchmark/corpus/fixtures/` into the headline number.

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/pages/SecurityReport.test.tsx`, inside the existing `describe`:

```tsx
  it("scopes the report to production files and accounts for the rest", () => {
    mockUseScan.mockReturnValue({
      currentReport: {
        files: [
          {
            name: "runner.py",
            path: "app/runner.py",
            fileType: "production",
            security: [{ type: "Command Injection", severity: "Critical", description: "d", file: "app/runner.py" }],
          },
          {
            name: "test_runner.py",
            path: "tests/test_runner.py",
            fileType: "test",
            security: [
              { type: "Hardcoded Secret", severity: "High", description: "d", file: "tests/test_runner.py" },
              { type: "Weak Hash", severity: "Low", description: "d", file: "tests/test_runner.py" },
            ],
          },
        ],
      } as unknown as ScanReport,
    });

    render(<SecurityReport />);

    expect(screen.getByText(/1 finding in production files/)).toBeInTheDocument();
    // Scoped, not hidden — a reader must be able to reconcile this with the tile.
    expect(screen.getByText(/2 further findings in test\/non-code files/)).toBeInTheDocument();
    expect(screen.queryByText("Hardcoded Secret")).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the test and watch it fail**

```bash
cd frontend && npx vitest run src/pages/SecurityReport.test.tsx
```

Expected: FAIL — the page currently lists all three findings and its subtitle reads "3 vulnerabilities detected".

- [ ] **Step 3: Scope the page and relabel the tile**

In `frontend/src/pages/SecurityReport.tsx`, replace the `allVulnerabilities` line with:

```tsx
  // The dashboard tile counts production files only, because the backend's
  // total_security_issues does (repository_review_engine.py:512-514) and it
  // feeds health_score. This page matches that scope so the two numbers agree,
  // and accounts for what it excluded rather than hiding it.
  const productionFiles = currentReport.files.filter((f) => f.fileType === "production");
  const allVulnerabilities = productionFiles.flatMap((f) => f.security);
  const excludedCount = currentReport.files
    .filter((f) => f.fileType !== "production")
    .reduce((n, f) => n + f.security.length, 0);
```

Replace the subtitle `<p>` under the page title with:

```tsx
        <p className="text-muted-foreground mt-1">
          {allVulnerabilities.length} finding{allVulnerabilities.length === 1 ? "" : "s"} in production files
        </p>
        {excludedCount > 0 && (
          <p className="text-xs text-muted-foreground/70 mt-1">
            {excludedCount} further finding{excludedCount === 1 ? "" : "s"} in test/non-code files, excluded from the score
          </p>
        )}
```

In `frontend/src/pages/ScanResults.tsx:80`, change the tile label:

```tsx
    { label: "Security (production)", value: summary.security_issues, icon: Shield, color: "text-destructive" },
```

At `:105`, change the sentence to match:

```tsx
                  {summary.security_issues} security finding{summary.security_issues === 1 ? "" : "s"} in production files
```

- [ ] **Step 4: Run the full suite and the typecheck**

```bash
cd frontend && npx vitest run && npm run typecheck
```

Expected: 57 tests across 11 files, all passing. Typecheck exits 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SecurityReport.tsx frontend/src/pages/SecurityReport.test.tsx frontend/src/pages/ScanResults.tsx
git commit -m "Make the security count mean the same thing on both screens"
git status --short
```

---

### Task 7: FileAnalysis drops its copy of the card

**Files:**
- Modify: `frontend/src/pages/FileAnalysis.tsx:266-284` (the inline issue block)

**Interfaces:**
- Consumes: `FindingCard` (Task 2), `fromFileIssue` (Task 1).
- Produces: nothing.

This is last on purpose — an additive checkpoint (CONSTRAINTS 16). The six commits that matter are already green and committed before the reference page changes, so a regression here cannot block them.

- [ ] **Step 1: Confirm the suite is green before touching anything**

```bash
cd frontend && npx vitest run
```

Expected: 57 passing. If it is not green, stop — this task's whole value is that it starts from a known-good tree.

- [ ] **Step 2: Replace the inline block**

In `frontend/src/pages/FileAnalysis.tsx`, add to the imports:

```tsx
import { FindingCard } from "@/components/FindingCard";
import { fromFileIssue } from "@/lib/findings";
```

Replace the `file.issues.map((issue, i) => (...))` expression — the outer `<div className="flex items-start gap-3 p-3 rounded-lg bg-secondary/20">` through its closing tag — with:

```tsx
                  {file.issues.map((issue, i) => (
                    <FindingCard key={i} finding={fromFileIssue(issue, file)} />
                  ))}
```

Remove the now-unused `SeverityBadge` and `TrustBoundaryBadge` imports **only if** nothing else in the file references them — check first, the file is 324 lines. `Badge` is used elsewhere in it; leave that import alone.

- [ ] **Step 3: Run the full suite, the typecheck and a production build**

```bash
cd frontend && npx vitest run && npm run typecheck && npm run build
```

Expected: 57 passing, typecheck exit 0, build succeeds. The build matters here because this page carries the heaviest imports in the app.

- [ ] **Step 4: Verify in a real browser**

```bash
cd frontend && npx vite
```

Load a report, open a file's analysis, and confirm the issue list still shows severity, message, Context, Fix, line, category and trust boundary. A whole-pixel screenshot is not sufficient evidence for layout here — BUG-001 lived at fractional widths that no headless viewport can express.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/FileAnalysis.tsx
git commit -m "Drop the duplicated issue block now that the card exists"
git status --short
```

---

## Final verification

Run from `frontend/`, and read the counts, not just the exit codes — a command that checked nothing exits 0 too.

```bash
npx vitest run          # expect 57 passed, 11 files
npm run typecheck       # expect exit 0 (tsc -b, never tsc --noEmit)
npm run build           # expect a successful build
npx playwright test     # expect 17 passed across 3 projects, unchanged
```

Then, before the session ends: update `docs/HANDOVER.md` sections 1 and 3, and append the J1 entry to `docs/DECISIONS.md` noting which model made the calls.

## Deferred to J2 and J3

Do not build these here.

- **J2:** F6 (clickable severity tiers anchoring to a group), F9's expand/collapse detail, the `snippet` field, and F16's a11y pass over the interactive elements those two add.
- **J3:** F4 and F5 — the code panes. Both decisions are already made and recorded in the spec: F5's prose comes from a structured change list replacing the string-counting at `heuristic_refactor_engine.py:265-281`, and F4's empty state says what was actually checked rather than implying a clean bill of health.
