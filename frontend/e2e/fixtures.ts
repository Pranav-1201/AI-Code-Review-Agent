import { expect, type Page } from "@playwright/test";

/**
 * Sidebar link text for each route, so tests can navigate client-side.
 *
 * page.goto() is a full reload, and ScanContext holds the current report in
 * plain useState with no persistence — so a goto wipes the scan and every page
 * falls back to its empty state. Clicking through the sidebar keeps the data.
 */
export const SIDEBAR_LINKS: Record<string, string> = {
  "/": "Repository Scanner",
  "/results": "Scan Results",
  "/overview": "Repository Overview",
  "/file-analysis": "File Analysis",
  "/security": "Security Report",
  "/quality": "Code Quality",
  "/dependencies": "Dependencies",
  "/duplicates": "Duplicates",
  "/ai-suggestions": "AI Suggestions",
  "/health": "Health Score",
  "/issues": "Issue Explorer",
  "/visualizations": "Visualizations",
  "/history": "Scan History",
  "/export": "Export Report",
  "/settings": "Settings",
};

/** Load the built-in demo report so pages have something to render. */
export async function loadDemo(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: /view a demo report/i }).click();
  await expect(page).toHaveURL(/\/results$/);
}

/**
 * Navigate by clicking the sidebar, preserving in-memory scan state.
 *
 * Below 768px the sidebar is a Radix Sheet that has to be opened first, so this
 * opens it when the link is not already on screen — which doubles as a check
 * that mobile navigation is actually reachable.
 */
export async function navigateTo(page: Page, path: string) {
  const title = SIDEBAR_LINKS[path];
  if (!title) throw new Error(`No sidebar link mapped for ${path}`);

  const link = page.getByRole("link", { name: title, exact: true });

  if (!(await link.isVisible().catch(() => false))) {
    await page
      .getByRole("banner")
      .getByRole("button", { name: /toggle sidebar/i })
      .click();

    // Wait for the drawer to finish opening. Clicking a link while the sheet is
    // still sliding in fails the actionability check as "element is not stable".
    await expect(page.getByRole("dialog")).toBeVisible();
  }

  await link.click();
  await expect(page).toHaveURL(new RegExp(`${path === "/" ? "/$" : path + "$"}`));

  // On mobile the drawer closes with an animation, and its links stay in the
  // DOM while it plays. Returning early would let the next navigation click a
  // link that is on its way out. No dialog exists at desktop width, so this
  // settles immediately there.
  await expect(page.getByRole("dialog")).toHaveCount(0);
}

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
