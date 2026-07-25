export interface FileIssue {
  message: string;
  severity: "Low" | "Medium" | "High" | "Critical";
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
  severity: "Low" | "Medium" | "High" | "Critical";
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

  riskLevel: "Low" | "Medium" | "High" | "Critical";

  vulnerabilities: string[];
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