# Phase D Frontend Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the frontend its first test harness, error boundary, code splitting, and mobile verification, and wire all of it into CI.

**Architecture:** Vitest runs jsdom unit tests over `src/**/*.test.{ts,tsx}`, configured inside the existing `vite.config.ts` so the `@` path alias has a single definition. Playwright runs `e2e/*.spec.ts` against a `vite preview` server serving the real production build, with every backend call intercepted by `page.route`. A class-based error boundary and a `Suspense` wrapper sit between `DashboardLayout` and `Routes`, so a lazy chunk that fails to load surfaces as the boundary's fallback instead of an unhandled rejection.

**Tech Stack:** React 18, TypeScript 5.8, Vite 5, Vitest 3, @testing-library/react 16, Playwright 1.58, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-17-phase-d-frontend-hardening-design.md`

## Global Constraints

- All frontend commands run from `D:\ETPROJECT\frontend`. All git commands run from `D:\ETPROJECT`.
- Branch is `phase-d/frontend-hardening`, based on `bf8b084`.
- **Never add AI/assistant attribution to a commit message.** No `Co-Authored-By` naming an assistant, no "Generated with" line. This is a project rule in `CLAUDE.md`.
- **Typecheck is `npx tsc -b`, never `tsc --noEmit`.** The root `tsconfig.json` is solution-style (`"files": []` plus references), so a plain invocation compiles zero files and exits 0 unconditionally.
- Dependency bumps are **targeted, one package at a time**. Do not run `npm audit fix` — it would also bump `react-router-dom`, which the spec explicitly excludes.
- `vite` stays at **5.4.21** for this phase. Its only advisory fix is `8.2.1`, a three-major upgrade; it is out of scope here and carries to phase E.
- `react-router-dom` stays at **6.30.3** for this phase, per the spec.
- Vitest `include` must stay narrowed to `src/**/*.test.{ts,tsx}`. Playwright specs use the `.spec.ts` suffix and live in `e2e/`. The two harnesses must never collect each other's files.
- Backend behaviour is out of scope. `pytest` must stay at 288 passed / 0 failed.

---

### Task 1: Bump the two in-range vulnerable devDependencies

**Files:**
- Modify: `frontend/package.json` (devDependencies)
- Modify: `frontend/package-lock.json` (generated)

**Interfaces:**
- Consumes: nothing.
- Produces: a `vitest` binary at 3.2.7, which every later task's `npm test` invokes.

This lands first because bumping build tooling can change `vite build` chunk output, and Task 5's entire evidence is a before/after chunk comparison. The baseline must be taken after this task, not before.

- [ ] **Step 1: Record the current audit state**

Run: `npm audit --omit=dev=false` (from `frontend/`)
Save the output. You need the "before" to prove the "after" changed something.

- [ ] **Step 2: Bump vitest to the highest 3.2.x**

Run:
```bash
npm install --save-dev vitest@3.2.7
```

3.2.7 is the newest release inside the existing `^3.2.4` range. `vitest@latest` is 4.1.10, a major bump; do not take it.

- [ ] **Step 3: Bump postcss to the highest 8.5.x**

Run:
```bash
npm install --save-dev postcss@8.5.26
```

- [ ] **Step 4: Verify the advisories actually cleared**

Run: `npm audit`
Expected: `vitest` no longer appears as Critical, and `postcss` no longer appears as High.
`vite` (High) and `react-router-dom` (moderate) SHOULD still appear — they are deliberately out of scope. If `vitest` is still flagged at 3.2.7, stop and report; it would mean the advisory has no in-range fix after all and the decision needs revisiting.

- [ ] **Step 5: Verify nothing broke**

Run:
```bash
npx tsc -b
npm run build
```
Expected: both exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "Bump vitest and postcss off their published advisories

vitest 3.2.4 carries a Critical (GHSA-5xrq-8626-4rwp) and postcss 8.5.6
a High. Phase D is about to make vitest load-bearing, so shipping a new
test suite on a Critical-CVE runner would be backwards. Both fixes are
available inside the existing semver range.

vite is left at 5.4.21 on purpose: its only fix is 8.2.1, three majors
up, which is a build-tool migration rather than a patch and would also
move the chunk-output baseline that the code-splitting work is about to
measure against. react-router-dom is left alone because this phase is
already rewriting the routing it backs."
```

---

### Task 2: Stand up the vitest harness and test the response mapper

**Files:**
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/lib/response-mapper.test.ts`

**Interfaces:**
- Consumes: `mapApiResponse(data: any, repoUrl: string): ScanReport` and `getDisplayName(file: FileAnalysis, allFiles: FileAnalysis[]): string`, both already exported from `src/lib/response-mapper.ts`.
- Produces: a working `npm test`, and `src/test/setup.ts` as the setup file every later unit test relies on for jest-dom matchers.

These are **characterization tests over code that already ships**. If a test reveals behaviour that looks wrong, report it — do not change `response-mapper.ts` in this task. A behaviour change smuggled into a commit labelled "add tests" is how regressions hide.

- [ ] **Step 1: Add the test block to the Vite config**

Replace the contents of `frontend/vite.config.ts` with:

```ts
/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react-swc";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
    hmr: {
      overlay: false,
    },
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    dedupe: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime"],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // Narrow on purpose. The default glob would also collect e2e/*.spec.ts,
    // where Playwright's `test` and `expect` are different objects from
    // vitest's — the two harnesses must not see each other's files.
    include: ["src/**/*.test.{ts,tsx}"],
  },
}));
```

`defineConfig` now comes from `vitest/config`, which re-exports Vite's own — so `vite build` is unaffected and the `@` alias stays defined exactly once, shared by both tools.

- [ ] **Step 2: Create the setup file**

Create `frontend/src/test/setup.ts`:

```ts
// Registers the jest-dom matchers (toBeInTheDocument, toHaveTextContent, ...)
// on vitest's expect. Referenced from vite.config.ts `test.setupFiles`.
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 3: Write the failing tests**

Create `frontend/src/lib/response-mapper.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { mapApiResponse, getDisplayName } from "./response-mapper";
import type { FileAnalysis } from "./types";

const REPO = "https://github.com/acme/widget";

describe("mapApiResponse — backend summary averages", () => {
  it("ignores a backend average of 0 and recomputes from production files", () => {
    // `??` alone would accept 0, because 0 is not nullish, and a degenerate
    // backend zero would then mask real production scores.
    const report = mapApiResponse(
      {
        summary: { average_quality_score: 0 },
        file_reports: [
          { file_path: "src/a.py", score: 80, file_type: "production" },
          { file_path: "src/b.py", score: 60, file_type: "production" },
        ],
      },
      REPO
    );

    expect(report.summary.avg_score).toBe(70);
  });

  it("trusts a positive backend average over the local computation", () => {
    const report = mapApiResponse(
      {
        summary: { average_quality_score: 42.5 },
        file_reports: [{ file_path: "src/a.py", score: 80, file_type: "production" }],
      },
      REPO
    );

    expect(report.summary.avg_score).toBe(42.5);
  });
});

describe("mapApiResponse — dependency advisories", () => {
  it("coerces a legacy bare CVE string into a Vulnerability object", () => {
    // Scans persisted before OSV enrichment stored bare id strings, and the
    // history page replays them. A raw string reaching the renderer is thrown
    // by React as an invalid child — this is what crashed the Dependency page.
    const report = mapApiResponse(
      {
        dependencies: [
          { name: "lodash", version: "4.17.20", vulnerabilities: ["CVE-2021-23337"] },
        ],
      },
      REPO
    );

    expect(report.dependencies[0].vulnerabilities).toEqual([
      { id: "CVE-2021-23337", summary: "", severity: "Unknown" },
    ]);
  });

  it("passes through advisory objects unchanged", () => {
    const report = mapApiResponse(
      {
        dependencies: [
          {
            name: "vitest",
            version: "3.2.4",
            vulnerabilities: [
              { id: "GHSA-5xrq-8626-4rwp", summary: "browser mode flaw", severity: "Critical" },
            ],
          },
        ],
      },
      REPO
    );

    expect(report.dependencies[0].vulnerabilities).toEqual([
      { id: "GHSA-5xrq-8626-4rwp", summary: "browser mode flaw", severity: "Critical" },
    ]);
  });

  it("returns an empty list when the backend sends no vulnerabilities field", () => {
    const report = mapApiResponse(
      { dependencies: [{ name: "flask", version: "3.0.0" }] },
      REPO
    );

    expect(report.dependencies[0].vulnerabilities).toEqual([]);
  });
});

describe("mapApiResponse — field-name fallback chains", () => {
  it("prefers file_reports when it is non-empty", () => {
    const report = mapApiResponse(
      {
        file_reports: [{ file_path: "chosen.py" }],
        reports: [{ file_path: "ignored.py" }],
      },
      REPO
    );

    expect(report.files.map((f) => f.name)).toEqual(["chosen.py"]);
  });

  it("falls back to reports when file_reports is an empty array", () => {
    const report = mapApiResponse(
      {
        file_reports: [],
        reports: [{ file_path: "fallback.py" }],
      },
      REPO
    );

    expect(report.files.map((f) => f.name)).toEqual(["fallback.py"]);
  });

  it("prefers repository_summary over summary", () => {
    const report = mapApiResponse(
      {
        repository_summary: { files_analyzed: 7 },
        summary: { files_analyzed: 99 },
      },
      REPO
    );

    expect(report.summary.files).toBe(7);
  });
});

describe("mapApiResponse — severity mapping", () => {
  const issueWithSeverity = (severity: string) =>
    mapApiResponse(
      { file_reports: [{ file_path: "a.py", issues: [{ message: "m", severity }] }] },
      REPO
    ).files[0].issues[0].severity;

  it("maps moderate to Medium", () => {
    expect(issueWithSeverity("moderate")).toBe("Medium");
  });

  it("preserves Info rather than collapsing it to Low", () => {
    // Info is the calmest tier (e.g. a code-exec sink reachable only from
    // local operator input). Collapsing it would overstate exploitability.
    expect(issueWithSeverity("Info")).toBe("Info");
  });

  it("floors an unrecognised severity to Low", () => {
    expect(issueWithSeverity("bananas")).toBe("Low");
  });

  it("maps critical case-insensitively", () => {
    expect(issueWithSeverity("CRITICAL")).toBe("Critical");
  });
});

describe("mapApiResponse — production-only counting", () => {
  it("counts security findings from production files only", () => {
    const report = mapApiResponse(
      {
        file_reports: [
          {
            file_path: "src/app.py",
            file_type: "production",
            security: [{ type: "sql_injection" }, { type: "weak_crypto" }],
          },
          {
            file_path: "tests/test_app.py",
            file_type: "test",
            security: [{ type: "hardcoded_secret" }, { type: "x" }, { type: "y" }],
          },
        ],
      },
      REPO
    );

    expect(report.summary.security_issues).toBe(2);
  });

  it("uses the backend total when it supplies one", () => {
    const report = mapApiResponse(
      {
        summary: { total_security_issues: 11 },
        file_reports: [
          { file_path: "src/app.py", file_type: "production", security: [{ type: "x" }] },
        ],
      },
      REPO
    );

    expect(report.summary.security_issues).toBe(11);
  });
});

describe("mapApiResponse — path handling", () => {
  it("normalises Windows backslashes to forward slashes", () => {
    const report = mapApiResponse(
      { file_reports: [{ file_path: "src\\pkg\\mod.py" }] },
      REPO
    );

    expect(report.files[0].path).toBe("src/pkg/mod.py");
    expect(report.files[0].name).toBe("mod.py");
  });

  it("derives repoName from the trailing URL segment", () => {
    const report = mapApiResponse({}, "https://github.com/acme/widget");
    expect(report.repoName).toBe("widget");
  });
});

describe("mapApiResponse — noise filtering", () => {
  it("drops the backend's 'no obvious structural issues' placeholder", () => {
    const report = mapApiResponse(
      {
        file_reports: [
          {
            file_path: "clean.py",
            issues: [
              { message: "No obvious structural issues found." },
              { message: "Real problem here" },
            ],
          },
        ],
      },
      REPO
    );

    expect(report.files[0].issues.map((i) => i.message)).toEqual(["Real problem here"]);
  });
});

describe("mapApiResponse — degenerate input", () => {
  it("maps an empty object without throwing", () => {
    const report = mapApiResponse({}, "");

    expect(report.files).toEqual([]);
    expect(report.dependencies).toEqual([]);
    expect(report.summary.files).toBe(0);
    expect(report.summary.avg_score).toBe(0);
    expect(report.repoName).toBe("repository");
    expect(typeof report.summary.healthScore).toBe("number");
  });
});

describe("getDisplayName", () => {
  const file = (path: string): FileAnalysis =>
    ({ name: path.split("/").pop()!, path } as FileAnalysis);

  it("returns the bare basename when it is unique", () => {
    const files = [file("src/alpha.py"), file("src/beta.py")];
    expect(getDisplayName(files[0], files)).toBe("alpha.py");
  });

  it("qualifies with the parent directory when basenames collide", () => {
    const files = [file("api/models.py"), file("web/models.py")];
    expect(getDisplayName(files[0], files)).toBe("api/models.py");
  });
});
```

- [ ] **Step 4: Run the tests to verify the harness works**

Run: `npm test`
Expected: all tests PASS. These characterize existing behaviour, so a red run means either the harness is misconfigured or the code does not do what its comments claim — investigate before proceeding, and report rather than edit `response-mapper.ts`.

**If the run fails to start at all** with a jsdom error: `jsdom` is pinned at 20.0.3 (2022) against vitest 3. Bump it with `npm install --save-dev jsdom@26` and note it in the commit message. It is a devDependency with no advisory implication.

- [ ] **Step 5: Verify the typecheck still passes**

Run: `npx tsc -b`
Expected: exit 0. This proves `types: ["vitest/globals"]` in `tsconfig.app.json` — previously dangling — now resolves.

- [ ] **Step 6: Commit**

```bash
git add frontend/vite.config.ts frontend/src/test/setup.ts frontend/src/lib/response-mapper.test.ts
git commit -m "Give the frontend a test harness, starting at its widest untyped seam

The frontend had no tests. package.json wired vitest and tsconfig.app.json
even declared vitest/globals, but nothing consumed either, and CI carried
a comment explaining that a test step would only produce a red run.

mapApiResponse is the first subject because it is the widest untyped
boundary in the app: ~130 lines of pure function turning an `any` backend
payload into ScanReport, with no I/O to mock. Two of its cases are
regressions of defects the file's own comments record -- a backend average
of 0 must lose to recomputation, and a legacy bare CVE string must be
coerced before it reaches React as an invalid child.

The test config lives in vite.config.ts rather than a separate
vitest.config.ts so the @ alias has one definition instead of two that can
drift. `include` is narrowed to src/**/*.test.* so vitest never collects
the Playwright specs added later."
```

---

### Task 3: Add the error boundary

**Files:**
- Create: `frontend/src/components/ErrorBoundary.tsx`
- Create: `frontend/src/components/ErrorBoundary.test.tsx`

**Interfaces:**
- Consumes: `Button` from `@/components/ui/button`; the vitest harness from Task 2.
- Produces: `export class ErrorBoundary extends Component<{ children: ReactNode }>`, mounted by Task 4.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ErrorBoundary.test.tsx`:

```tsx
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { ErrorBoundary } from "./ErrorBoundary";

function Boom(): JSX.Element {
  throw new Error("kaboom");
}

afterEach(cleanup);

describe("ErrorBoundary", () => {
  it("renders its children when nothing throws", () => {
    render(
      <ErrorBoundary>
        <p>all good</p>
      </ErrorBoundary>
    );

    expect(screen.getByText("all good")).toBeInTheDocument();
  });

  it("renders the fallback in place of a child that throws", () => {
    // React logs every caught error to console.error by design. Silence it so
    // an expected error does not look like a broken test run.
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    );

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/kaboom/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();

    spy.mockRestore();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm test -- ErrorBoundary`
Expected: FAIL — `Failed to resolve import "./ErrorBoundary"`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/ErrorBoundary.tsx`:

```tsx
import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches render-time throws below it and shows a recoverable fallback.
 *
 * Mounted INSIDE DashboardLayout, wrapping <Routes> — not at the root. That
 * placement is the point: at the root, one page's throw takes the sidebar and
 * header with it and the user's only recourse is the browser back button. Here,
 * the chrome survives and the user can navigate away from the broken page.
 *
 * React offers no hook equivalent, so this stays a class component.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled render error:", error, info.componentStack);
  }

  private handleReset = () => {
    this.setState({ error: null });
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div
        role="alert"
        className="max-w-xl mx-auto mt-12 rounded-lg border border-destructive/40 bg-destructive/10 p-6 space-y-4"
      >
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-destructive shrink-0" aria-hidden="true" />
          <h2 className="text-lg font-semibold">This page hit an error</h2>
        </div>

        <p className="text-sm text-muted-foreground">
          The rest of the app is still working — use the sidebar to go somewhere else,
          or try rendering this page again.
        </p>

        <p className="font-mono text-xs break-words opacity-80">{error.message}</p>

        <div className="flex gap-3">
          <Button onClick={this.handleReset}>Try again</Button>
          <Button variant="outline" asChild>
            <a href="/">Back to scanner</a>
          </Button>
        </div>
      </div>
    );
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm test -- ErrorBoundary`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ErrorBoundary.tsx frontend/src/components/ErrorBoundary.test.tsx
git commit -m "Stop one page's throw from white-screening the whole app

There was no error boundary anywhere, so any render-time throw took the
entire application down, sidebar and navigation included, leaving the
browser back button as the only way out.

Mounted inside DashboardLayout rather than at the root, so the chrome
survives and the user can navigate away from the broken page unaided.
The fallback also offers a reset, because a transient failure should not
require a reload."
```

---

### Task 4: Split the routes

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `ErrorBoundary` from Task 3.
- Produces: no new exports. Later tasks depend on the built chunks existing.

- [ ] **Step 1: Capture the baseline chunk manifest**

Run: `npm run build`
Record the reported chunk names and sizes. This is the "before" half of the only evidence that splitting worked.

- [ ] **Step 2: Rewrite App.tsx**

Replace the contents of `frontend/src/App.tsx` with:

```tsx
import { lazy, Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import * as TooltipProvider from "@radix-ui/react-tooltip";
import { Loader2 } from "lucide-react";
import { ScanProvider } from "@/context/ScanContext";
import { DashboardLayout } from "@/components/DashboardLayout";
import { ErrorBoundary } from "@/components/ErrorBoundary";

// The landing route stays eager: it is the first paint, and a loading
// fallback there would be a flash of nothing on every cold visit.
import RepositoryScanner from "@/pages/RepositoryScanner";

// Everything else is lazy. These pages pull recharts, react-markdown and the
// dependency-graph renderer, all of which used to sit in the entry chunk.
const ScanResults = lazy(() => import("@/pages/ScanResults"));
const RepositoryOverview = lazy(() => import("@/pages/RepositoryOverview"));
const FileAnalysis = lazy(() => import("@/pages/FileAnalysis"));
const SecurityReport = lazy(() => import("@/pages/SecurityReport"));
const CodeQuality = lazy(() => import("@/pages/CodeQuality"));
const DependencyAnalysis = lazy(() => import("@/pages/DependencyAnalysis"));
const AISuggestions = lazy(() => import("@/pages/AISuggestions"));
const HealthScore = lazy(() => import("@/pages/HealthScore"));
const ScanHistory = lazy(() => import("@/pages/ScanHistory"));
const IssueExplorer = lazy(() => import("@/pages/IssueExplorer"));
const DuplicateDetection = lazy(() => import("@/pages/DuplicateDetection"));
const Visualizations = lazy(() => import("@/pages/Visualizations"));
const ExportReport = lazy(() => import("@/pages/ExportReport"));
const Settings = lazy(() => import("@/pages/Settings"));
const NotFound = lazy(() => import("@/pages/NotFound"));

const queryClient = new QueryClient();

function RouteFallback() {
  return (
    <div className="flex items-center justify-center py-24" role="status" aria-live="polite">
      <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" aria-hidden="true" />
      <span className="sr-only">Loading page</span>
    </div>
  );
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider.Provider>
      <Toaster richColors position="top-right" />
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ScanProvider>
          <DashboardLayout>
            {/* Boundary outside Suspense: a chunk that fails to download is a
                render-time throw, and this way it surfaces as the recoverable
                fallback instead of an unhandled rejection. */}
            <ErrorBoundary>
              <Suspense fallback={<RouteFallback />}>
                <Routes>
                  <Route path="/" element={<RepositoryScanner />} />
                  <Route path="/results" element={<ScanResults />} />
                  <Route path="/overview" element={<RepositoryOverview />} />
                  <Route path="/file-analysis" element={<FileAnalysis />} />
                  <Route path="/security" element={<SecurityReport />} />
                  <Route path="/quality" element={<CodeQuality />} />
                  <Route path="/dependencies" element={<DependencyAnalysis />} />
                  <Route path="/ai-suggestions" element={<AISuggestions />} />
                  <Route path="/health" element={<HealthScore />} />
                  <Route path="/history" element={<ScanHistory />} />
                  <Route path="/issues" element={<IssueExplorer />} />
                  <Route path="/duplicates" element={<DuplicateDetection />} />
                  <Route path="/visualizations" element={<Visualizations />} />
                  <Route path="/export" element={<ExportReport />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </ErrorBoundary>
          </DashboardLayout>
        </ScanProvider>
      </BrowserRouter>
    </TooltipProvider.Provider>
  </QueryClientProvider>
);

export default App;
```

- [ ] **Step 3: Verify the typecheck passes**

Run: `npx tsc -b`
Expected: exit 0.

If a page has no default export, `lazy(() => import(...))` fails to typecheck. Every page currently uses `export default`, so this should pass; if one does not, fix that page's export rather than reverting it to eager.

- [ ] **Step 4: Build and compare against the baseline**

Run: `npm run build`
Expected: many more chunk files than before, and the entry chunk measurably smaller than the size recorded in Step 1. **If the entry chunk did not shrink, the splitting did not work** — investigate before committing, regardless of how the source reads.

- [ ] **Step 5: Verify the unit suite still passes**

Run: `npm test`
Expected: all pass.

- [ ] **Step 6: Commit**

Include the before/after entry chunk sizes in the message, substituting the real numbers recorded above.

```bash
git add frontend/src/App.tsx
git commit -m "Load routes on demand instead of shipping all sixteen up front

Every route was a static import, so the entry chunk carried recharts,
react-markdown and the dependency-graph renderer whether or not the
visitor ever opened a page that used them.

Fifteen routes become React.lazy behind one Suspense. The landing route
stays eager, because a fallback on first paint is a regression, not an
improvement. The boundary sits outside Suspense so a chunk that fails to
download lands in the recoverable fallback rather than an unhandled
rejection.

Entry chunk: <BEFORE> -> <AFTER>."
```

---

### Task 5: Playwright config and the smoke spec

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/fixtures.ts`
- Create: `frontend/e2e/smoke.spec.ts`
- Modify: `frontend/package.json` (add `test:e2e` script)

**Interfaces:**
- Consumes: the production build from Task 4.
- Produces: `mockBackend(page: Page): Promise<void>` and `scanResult`, both from `e2e/fixtures.ts`, reused by Task 6.

- [ ] **Step 1: Install the chromium browser binary**

Run: `npx playwright install chromium`

This is a ~140MB download; the local `ms-playwright` cache is currently empty. It is a one-time cost.

- [ ] **Step 2: Write the Playwright config**

Create `frontend/playwright.config.ts`:

```ts
import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;
const BASE_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "list",

  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },

  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    {
      name: "tablet-768",
      use: { ...devices["Desktop Chrome"], viewport: { width: 768, height: 1024 } },
    },
    {
      name: "mobile-375",
      use: { ...devices["Desktop Chrome"], viewport: { width: 375, height: 812 } },
    },
  ],

  // `vite preview` serves the PRODUCTION build. The dev server would serve
  // unbundled modules and so would never exercise the lazy chunks under test.
  webServer: {
    command: `npm run build && npx vite preview --port ${PORT} --strictPort`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
```

- [ ] **Step 3: Write the fixtures**

Create `frontend/e2e/fixtures.ts`:

```ts
import type { Page } from "@playwright/test";

/**
 * A minimal but realistic /scan result. Shapes are taken from what
 * response-mapper.ts actually reads, not invented.
 */
export const scanResult = {
  repository_summary: {
    files_analyzed: 2,
    files_with_issues: 1,
    average_quality_score: 74,
    total_security_issues: 1,
    total_lines: 180,
    health_score: 68,
    avg_documentation_coverage: 55,
    avg_cyclomatic_complexity: 4,
    production_files: 1,
    test_files: 1,
  },
  file_reports: [
    {
      file_path: "src/app.py",
      file_type: "production",
      language: "python",
      score: 74,
      lines_of_code: 120,
      cyclomatic_complexity: 4,
      documentation_coverage: 55,
      explanation: "Handles request routing.",
      suggestions: ["Extract the validation helper."],
      issues: [
        {
          message: "Function exceeds recommended length",
          severity: "Medium",
          type: "maintainability",
          line: 42,
        },
      ],
      security: [
        {
          type: "command_injection",
          severity: "High",
          description: "Shell invocation built from a request parameter",
          line: 88,
          recommendation: "Pass an argument list and never use shell=True.",
        },
      ],
    },
    {
      file_path: "tests/test_app.py",
      file_type: "test",
      language: "python",
      score: 90,
      lines_of_code: 60,
      issues: [],
      security: [],
    },
  ],
  dependencies: [
    {
      name: "lodash",
      version: "4.17.20",
      latest_version: "4.17.21",
      is_outdated: true,
      risk_level: "High",
      vulnerabilities: [
        { id: "CVE-2021-23337", summary: "Command injection in template", severity: "High" },
      ],
    },
  ],
  dependency_graph: {
    nodes: [{ id: "src/app.py" }, { id: "tests/test_app.py" }],
    links: [{ source: "tests/test_app.py", target: "src/app.py" }],
  },
  duplicates: [],
};

const sse = (payload: unknown) => `data: ${JSON.stringify(payload)}\n\n`;

/**
 * Intercepts every backend call the frontend makes. Registration order
 * matters: Playwright matches the MOST RECENTLY registered route first, so
 * the specific patterns go last.
 */
export async function mockBackend(page: Page) {
  await page.route("**/settings", (route) => route.fulfill({ json: {} }));

  await page.route("**/scans", (route) => route.fulfill({ json: [] }));

  await page.route("**/scan", (route) =>
    route.fulfill({ json: { scan_id: "e2e-scan-1" } })
  );

  // Polling fallback path. `*` does not cross a slash, so this does not
  // capture /scan/:id/stream.
  await page.route("**/scan/*", (route) =>
    route.fulfill({ json: { status: "complete", result: scanResult } })
  );

  await page.route("**/scan/*/stream", (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream", "cache-control": "no-cache" },
      body:
        sse({ status: "running", stage: "analysis", progress: 60, stage_detail: "Analyzing" }) +
        sse({ status: "complete", result: scanResult }),
    })
  );
}
```

- [ ] **Step 4: Write the smoke spec**

Create `frontend/e2e/smoke.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { mockBackend } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockBackend(page);
});

test("the landing route renders", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Repository Scanner" })).toBeVisible();
});

test("a scan runs and lands on the results route", async ({ page }) => {
  await page.goto("/");

  await page.getByPlaceholder("https://github.com/username/repository").fill(
    "https://github.com/acme/widget"
  );
  await page.getByRole("button", { name: "Scan" }).click();

  await expect(page).toHaveURL(/\/results$/, { timeout: 30_000 });
});

test("lazily-loaded routes resolve", async ({ page }) => {
  // Each of these lives in its own chunk after the code-splitting change. A
  // chunk that fails to load renders the error boundary, so asserting the
  // boundary is absent is a real assertion, not a formality.
  for (const path of ["/security", "/dependencies", "/visualizations"]) {
    await page.goto(path);
    await expect(page.getByRole("status")).toHaveCount(0, { timeout: 15_000 });
    await expect(page.getByRole("alert")).toHaveCount(0);
  }
});
```

- [ ] **Step 5: Add the npm script**

In `frontend/package.json`, add to `scripts`:

```json
"test:e2e": "playwright test"
```

- [ ] **Step 6: Run the smoke spec**

Run: `npm run test:e2e -- smoke`
Expected: all pass across the three viewport projects.

**If the SSE test is flaky**, apply the documented fallback: change the `**/scan/*/stream` route to `route.fulfill({ status: 404 })`. `api.ts` already falls back to polling `/scan/:id` on any stream failure, and that route is mocked regardless. Record the switch in the commit message.

- [ ] **Step 7: Commit**

```bash
git add frontend/playwright.config.ts frontend/e2e/fixtures.ts frontend/e2e/smoke.spec.ts frontend/package.json
git commit -m "Add an end-to-end smoke test over the production build

Nothing verified that the app boots, that a scan reaches the results page,
or that the newly-split chunks actually load. The unit suite cannot answer
any of those.

Runs against `vite preview`, not the dev server: the dev server serves
unbundled modules and so would never exercise the lazy chunks this is
partly here to test. Every backend call is intercepted, so the suite needs
no Python, no Redis and no network -- the backend contract stays covered
by the 288 pytest tests. The tradeoff is that these fixtures can drift from
the real contract; they are derived from the shapes api.ts and
response-mapper.ts actually read, to keep that drift visible."
```

---

### Task 6: The mobile viewport spec

**Files:**
- Create: `frontend/e2e/mobile.spec.ts`

**Interfaces:**
- Consumes: `mockBackend` from `e2e/fixtures.ts` (Task 5).
- Produces: nothing later tasks consume.

- [ ] **Step 1: Write the spec**

Create `frontend/e2e/mobile.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { mockBackend } from "./fixtures";

const ROUTES = [
  "/",
  "/results",
  "/overview",
  "/file-analysis",
  "/security",
  "/quality",
  "/dependencies",
  "/ai-suggestions",
  "/health",
  "/history",
  "/issues",
  "/duplicates",
  "/visualizations",
  "/export",
  "/settings",
  "/does-not-exist",
];

// Only the narrow projects. Running these at desktop width would assert
// nothing interesting and would triple the runtime for no coverage.
test.skip(({ }, testInfo) => testInfo.project.name === "desktop");

test.beforeEach(async ({ page }) => {
  await mockBackend(page);

  // Populate the app with data via the built-in demo, so every route has
  // something to lay out. Going through a real scan on all sixteen routes
  // would be slower and would test the scan flow sixteen times over.
  await page.goto("/");
  await page.getByRole("button", { name: /view a demo report/i }).click();
  await expect(page).toHaveURL(/\/results$/);
});

for (const path of ROUTES) {
  test(`no horizontal overflow at ${path}`, async ({ page }) => {
    await page.goto(path);

    // Wait out the lazy chunk before measuring; a Suspense fallback has a
    // different layout from the page it stands in for.
    await expect(page.getByRole("status")).toHaveCount(0, { timeout: 15_000 });

    const overflow = await page.evaluate(() => {
      const el = document.documentElement;
      return el.scrollWidth - el.clientWidth;
    });

    // 1px of slack absorbs sub-pixel rounding on fractional viewport scaling.
    expect(overflow, `horizontal overflow at ${path}`).toBeLessThanOrEqual(1);
  });
}

test("the sidebar can be opened at a narrow width", async ({ page }) => {
  await page.goto("/");

  // DashboardLayout renders SidebarTrigger in the sticky header. If it is not
  // reachable, navigation is unavailable on mobile and the app is unusable
  // there regardless of what any single page looks like.
  const trigger = page.getByRole("button", { name: /toggle sidebar/i });
  await expect(trigger).toBeVisible();
  await trigger.click();
});
```

- [ ] **Step 2: Run the spec**

Run: `npm run test:e2e -- mobile`
Expected: all pass at both 768px and 375px.

**Failures here are the point of the task** — they are real layout bugs. Fix the offending page's CSS (the usual culprits are fixed-width tables, `min-w-` values on grids, and unwrapped `font-mono` strings) and re-run. Do not widen the tolerance to make a real overflow pass.

If the sidebar trigger's accessible name is not "Toggle Sidebar", read `src/components/ui/sidebar.tsx` for the real one and use it rather than loosening the selector to something that cannot fail.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/mobile.spec.ts
git commit -m "Assert every route survives 375px and 768px

The frontend had never been checked at a mobile width. This walks all
sixteen routes at both widths and fails on horizontal overflow, plus
checks the sidebar trigger is reachable -- without it, navigation is gone
on mobile no matter how any single page looks.

Assertions rather than screenshots on purpose: a screenshot review is a
one-time audit that stops protecting anything the moment it finishes,
where this keeps failing every time someone reintroduces a fixed-width
element. It cannot catch 'ugly but not broken'; that is the accepted
limit.

Data comes from the built-in demo rather than a mocked scan per route,
which would test the scan flow sixteen times to no purpose."
```

---

### Task 7: Wire it all into CI

**Files:**
- Modify: `.github/workflows/ci.yml:107-113`

**Interfaces:**
- Consumes: `npm test` (Task 2), `npm run test:e2e` (Task 5).
- Produces: nothing.

- [ ] **Step 1: Replace the frontend job's tail**

In `.github/workflows/ci.yml`, replace the `Production build` step and the trailing `NOTE:` comment block with:

```yaml
      - name: Production build
        run: npm run build

      - name: Unit tests
        run: npm test

      - name: Install Playwright browser
        # Only chromium. The suite targets one engine across three viewports,
        # so downloading firefox and webkit would cost time and prove nothing.
        run: npx playwright install --with-deps chromium

      - name: End-to-end and mobile viewport tests
        # playwright.config.ts starts its own `vite preview` server against the
        # production build, so no separate serve step is needed here.
        run: npm run test:e2e

      - name: Upload Playwright report on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: frontend/playwright-report/
          retention-days: 7
```

The `NOTE: no npm test step` comment must be **deleted**, not amended: it documents a condition this phase removes, and a comment that outlives its condition is worse than none.

- [ ] **Step 2: Confirm the workflow parses**

Run: `npx --yes js-yaml .github/workflows/ci.yml > /dev/null` from `D:\ETPROJECT`, or open the file and confirm the indentation matches the surrounding steps (six spaces before `- name:`).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "Run the frontend tests in CI

The frontend job typechecked and built but ran no tests, because until now
there were none to run. Adds the unit suite and the Playwright suite, and
uploads the Playwright report when a run fails so a red CI is diagnosable
without reproducing locally.

Only chromium is installed: the suite targets one engine across three
viewports, so fetching firefox and webkit would cost time and prove
nothing. Job count stays at two."
```

---

### Task 8: Full verification and branch push

**Files:** none modified.

- [ ] **Step 1: Run the complete backend suite**

Run from `D:\ETPROJECT`: `python -m pytest -q`
Expected: 288 passed, 0 failed. Phase D touches no backend code; anything else means something unexpected happened.

- [ ] **Step 2: Run the detector gate**

Run: `python backend/benchmark/run_benchmark.py --gate`
Expected: exit 0.

- [ ] **Step 3: Run every frontend check**

Run from `D:\ETPROJECT\frontend`:
```bash
npx tsc -b
npm run build
npm test
npm run test:e2e
```
Expected: all exit 0.

- [ ] **Step 4: Confirm the advisory state changed**

Run: `npm audit`
Expected: `vitest` and `postcss` cleared; `vite` and `react-router-dom` still listed, both deliberately deferred.

- [ ] **Step 5: Push the branch**

```bash
git push -u origin phase-d/frontend-hardening
```

- [ ] **Step 6: Confirm CI is green**

Run: `gh run list --branch phase-d/frontend-hardening --limit 1`
Then: `gh run watch <run-id>`

Expected: both jobs green. CI runs on Linux; this suite has only ever run on Windows. The pool-test incident in `bf8b084` is the precedent — a test that passed on the dev OS and failed on the CI runner. Treat the first CI run as the real verification, not a formality.

**Do not merge to `main` without asking.** The repository owner decides when the branch lands.

---

## Self-Review

**Spec coverage:**

| Spec item | Task |
|---|---|
| Test harness (vite.config.ts, setup.ts, narrowed include) | 2 |
| Response mapper unit tests (all 8 case groups) | 2 |
| Error boundary + placement inside DashboardLayout | 3, 4 |
| Route code splitting, `/` eager | 4 |
| Playwright config against `vite preview` | 5 |
| E2E smoke with mocked backend | 5 |
| Mobile assertions at 375/768 | 6 |
| CI wiring, NOTE comment deleted | 7 |
| devDep CVE bumps | 1 |
| Full verification | 8 |

One spec deviation, recorded in Global Constraints: the spec named `vite` among the bumps, but `npm audit` shows its only fix is the semver-major 8.2.1. It is deferred to phase E rather than turning a testing phase into a build-tool migration.

**Placeholder scan:** the only intentional placeholders are `<BEFORE>` and `<AFTER>` in Task 4's commit message, which are measurements that cannot exist until the step runs, and `<run-id>` in Task 8.

**Type consistency:** `mockBackend(page: Page)` and `scanResult` are defined in Task 5 and consumed under those exact names in Task 6. `ErrorBoundary` is a named (not default) export in Task 3 and imported as `{ ErrorBoundary }` in Task 4. `mapApiResponse` and `getDisplayName` match the existing exports in `response-mapper.ts`.
