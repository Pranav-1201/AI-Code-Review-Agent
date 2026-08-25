/**
 * Finding severity. "Info" is the calmest tier — e.g. a code-exec sink that
 * taint analysis proved is reachable only from local operator input, not from
 * remote/untrusted input. Kept distinct so the UI does not collapse it to Low.
 */
export type Severity = "Info" | "Low" | "Medium" | "High" | "Critical";

export interface FileIssue {
  message: string;
  severity: Severity;
  category: "security" | "performance" | "style" | "logic" | "maintainability";
  line?: number;
  why_it_matters?: string;
  how_to_fix?: string;
  snippet?: string;
  confidence?: number;
  trust_boundary?: string;   // Phase 3: untrusted_input | operator_input | parameter | internal | n/a
}

export interface SecurityVulnerability {
  type: string;
  severity: Severity;
  description: string;
  file: string;
  line?: number;
  recommendation?: string;
  why_it_matters?: string;
  how_to_fix?: string;
  snippet?: string;
  confidence?: number;
  trust_boundary?: string;   // Phase 3: untrusted_input | operator_input | parameter | internal | n/a
}

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

export interface FileAnalysis {
  name: string;
  path: string;

  score: number;

  issues: FileIssue[];
  security: SecurityVulnerability[];

  cyclomaticComplexity: number;
  maxCyclomaticComplexity: number;
  maxNestingDepth: number;
  branches: number;

  /** Estimated time-complexity string (e.g. "O(n)"), from the backend. */
  complexity?: string;

  breakdown?: Record<string, number>;

  linesOfCode: number;

  explanation: string;
  /** Which layer produced `explanation`: "llm" (Anthropic) or "deterministic". */
  explanationSource?: string;
  suggestions: string[];

  improved_code: string;
  original_code: string;
  patch: string | null;
  /** Empty for scans recorded before J3 added change tracking. */
  refactorChanges?: RefactorChange[];

  language: string;

  duplicates?: { file: string; similarity: number }[];

  documentationCoverage: number;

  /** Coarse classification (scoring + display): "production" | "test" | "non_code" */
  fileType: "production" | "test" | "non_code";

  /** Fine 5-tier backend role, surfaced for display. Optional for backward compat. */
  fileRole?: "utility" | "orchestrator" | "cli_parser" | "data_model" | "test" | "non_code";
}

export interface Dependency {
  name: string;
  version: string;

  latestVersion: string;

  isOutdated: boolean;

  riskLevel: Severity;

  vulnerabilities: Vulnerability[];

  /**
   * How the vulnerability lookup went (Phase H / S5).
   *
   * An empty `vulnerabilities` array means three different things, and the UI
   * must not render them alike: `checked` is a real all-clear, `unreachable`
   * means OSV could not be reached, and `skipped` means the version was never
   * resolved so nothing was asked.
   */
  vulnLookup: "checked" | "unreachable" | "skipped";

  /** The specifier as written in the manifest, e.g. ">=2.0". Empty if none. */
  constraint: string;

  /** How `version` was arrived at (Phase H / S7). */
  versionSource: "pinned" | "lockfile" | "unpinned" | "unspecified";
}

/**
 * One OSV.dev advisory. The backend has always sent objects of this shape;
 * this type previously claimed `string[]`, which the `any`-typed response
 * mapper hid from the compiler.
 */
export interface Vulnerability {
  id: string;
  summary: string;
  severity: string;
}

/* ---------------------------------- */
/* Architecture Graph (Phase 8) */
/* ---------------------------------- */

export interface DependencyGraph {
  nodes: {
    id: string;
  }[];

  links: {
    source: string;
    target: string;
  }[];
}

export interface ScanReport {

  id: string;

  repoUrl: string;

  repoName: string;

  timestamp: string;

  summary: {
    files: number;
    files_with_issues: number;

    avg_score: number;

    security_issues: number;

    totalLines: number;

    languages: {
      name: string;
      percentage: number;
      color: string;
    }[];

    healthScore: number;

    avg_documentation_coverage?: number;
    avg_cyclomatic_complexity?: number;

    production_files?: number;
    test_files?: number;

    maintainability_warnings?: {
      file: string;
      type: string;
      message: string;
      severity: string;
    }[];
  };

  insights?: {
    top_critical_issues: any[];
    most_complex_files: any[];
    most_central_file: string;
    most_reused_module: string;
  };

  files: FileAnalysis[];

  dependencies: Dependency[];

  /* Phase 8 */
  dependency_graph?: DependencyGraph;

  /* Duplicate detection results */
  duplicates?: { file1: string; file2: string; similarity: number; type?: string }[];
}

export interface ScanHistoryItem {

  id: string;

  repoName: string;

  repoUrl: string;

  timestamp: string;

  healthScore: number;

  filesAnalyzed: number;

  issuesFound: number;
}

export interface TestResult {
  name: string;
  status: "passed" | "failed" | "skipped";
  duration: number;
  module: string;
}