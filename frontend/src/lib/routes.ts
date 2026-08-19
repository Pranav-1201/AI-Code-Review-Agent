/**
 * The route table — the single source of truth for every path in the app.
 *
 * Five things need this list, and before this file existed it was written out
 * twice by hand (App.tsx's <Routes>, AppSidebar.tsx's nav groups) with a third
 * copy about to be added to the Caddyfile:
 *
 *   1. App.tsx          — which component renders at which path
 *   2. AppSidebar.tsx   — the nav, grouped and in order
 *   3. RouteHead        — per-page <title> and <meta name="description">
 *   4. vite-plugin-seo  — one <url><loc> per indexable path in sitemap.xml
 *   5. Caddyfile        — which paths get the SPA shell and which return 404
 *
 * Caddy cannot import TypeScript, so its copy is a genuine mirror. That is
 * exactly what routes.test.ts exists to police: change this file without
 * changing the Caddyfile and the test fails, naming both lists.
 *
 * ---------------------------------------------------------------------------
 * THIS FILE MUST NOT IMPORT ANYTHING.
 *
 * vite.config.ts imports it in Node, at build time, to generate the sitemap. A
 * React import, JSX, or `import.meta.env` access here turns that into a build
 * failure. Icons therefore stay in AppSidebar.tsx and lazy component imports
 * stay in App.tsx — both keyed by the paths below. routes.test.ts asserts the
 * import list is empty so this cannot regress quietly.
 * ---------------------------------------------------------------------------
 */

/** Sidebar section a route belongs to. `null` keeps it out of the nav. */
export type NavGroup = "Scan" | "Analysis" | "Insights" | "System";

export type RouteMeta = {
  /** URL path, exactly as React Router, the sidebar, and Caddy all see it. */
  path: string;
  /**
   * Page name. Used verbatim as the sidebar label, and as the <title> with the
   * site name appended.
   */
  title: string;
  /** <meta name="description">. Specific to the page; never filler. */
  description: string;
  /**
   * False keeps the path out of sitemap.xml and emits <meta name="robots"
   * content="noindex">. The path is still routed and still served — this is
   * about crawlers, not access.
   */
  indexable: boolean;
  /** Sidebar section, or null for a route that is not in the nav. */
  navGroup: NavGroup | null;
};

export const SITE_NAME = "AI Code Review";

/**
 * Order is load-bearing: AppSidebar renders groups in first-appearance order
 * and items in array order, so this array's order IS the nav's order.
 */
export const ROUTES: readonly RouteMeta[] = [
  {
    path: "/",
    title: "Repository Scanner",
    description:
      "Scan a public Git repository for security vulnerabilities, code quality issues, and dependency risks.",
    indexable: true,
    navGroup: "Scan",
  },
  {
    path: "/results",
    title: "Scan Results",
    description:
      "Summary of the most recent scan: severity breakdown, affected files, and overall repository health.",
    indexable: true,
    navGroup: "Scan",
  },
  {
    path: "/overview",
    title: "Repository Overview",
    description:
      "Repository structure, language breakdown, and size metrics gathered during the scan.",
    indexable: true,
    navGroup: "Scan",
  },
  {
    path: "/file-analysis",
    title: "File Analysis",
    description:
      "Per-file findings, complexity metrics, and the issues detected in each source file.",
    indexable: true,
    navGroup: "Analysis",
  },
  {
    path: "/security",
    title: "Security Report",
    description:
      "Security findings by severity: injection risks, unsafe deserialization, hardcoded secrets, and known vulnerable dependencies.",
    indexable: true,
    navGroup: "Analysis",
  },
  {
    path: "/quality",
    title: "Code Quality",
    description:
      "Maintainability signals: complexity, dead code, long functions, and structural problems worth refactoring.",
    indexable: true,
    navGroup: "Analysis",
  },
  {
    path: "/dependencies",
    title: "Dependencies",
    description:
      "Dependency graph and advisory matches for the packages this repository depends on.",
    indexable: true,
    navGroup: "Analysis",
  },
  {
    path: "/duplicates",
    title: "Duplicates",
    description:
      "Duplicated and near-duplicated code blocks, with the files and line ranges that share them.",
    indexable: true,
    navGroup: "Analysis",
  },
  {
    path: "/ai-suggestions",
    title: "AI Suggestions",
    description:
      "Suggested fixes for the findings in this scan, with the reasoning behind each one.",
    indexable: true,
    navGroup: "Insights",
  },
  {
    path: "/health",
    title: "Health Score",
    description:
      "Overall repository health score and the security, quality, and dependency factors it is built from.",
    indexable: true,
    navGroup: "Insights",
  },
  {
    path: "/issues",
    title: "Issue Explorer",
    description:
      "Every finding in one place, filterable by severity, category, and file.",
    indexable: true,
    navGroup: "Insights",
  },
  {
    path: "/visualizations",
    title: "Visualizations",
    description:
      "Charts for issue distribution, severity mix, and how findings are spread across the codebase.",
    indexable: true,
    navGroup: "Insights",
  },
  {
    path: "/history",
    title: "Scan History",
    description:
      "Previous scans, with their status and results, so you can compare a repository over time.",
    indexable: true,
    navGroup: "System",
  },
  {
    path: "/export",
    title: "Export Report",
    description:
      "Download the results of a scan as a shareable report.",
    indexable: true,
    navGroup: "System",
  },
  {
    path: "/settings",
    title: "Settings",
    // noindex: a preferences screen has nothing to rank for, and indexing it
    // spends crawl budget on a page no search result should ever point at.
    description: "Configure scan behaviour and application preferences.",
    indexable: false,
    navGroup: "System",
  },
];

/** Look up a route by exact path. Returns undefined for unknown paths. */
export function routeFor(path: string): RouteMeta | undefined {
  return ROUTES.find((route) => route.path === path);
}
