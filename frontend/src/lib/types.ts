export interface FileIssue {
  message: string;
  severity: "Low" | "Medium" | "High" | "Critical";
  category: "security" | "performance" | "style" | "logic" | "maintainability";
  line?: number;
}

export interface SecurityVulnerability {
  type: string;
  severity: "Low" | "Medium" | "High" | "Critical";
  description: string;
  file: string;
  line?: number;
  recommendation: string;
}

export interface FileAnalysis {
  name: string;
  path: string;

  score: number;

  issues: FileIssue[];
  security: SecurityVulnerability[];

  complexity: string;
  cyclomaticComplexity: number;
  maxCyclomaticComplexity: number;

  linesOfCode: number;

  explanation: string;
  suggestions: string[];

  improved_code: string;
  original_code: string;
  patch: string | null;

  language: string;

  duplicates?: { file: string; similarity: number }[];

  documentationCoverage: number;

  /** Classification: "production" | "test" | "non_code" */
  fileType: "production" | "test" | "non_code";
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