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

  linesOfCode: number;

  explanation: string;
  suggestions: string[];

  improved_code: string;
  original_code: string;
  patch: string | null;

  language: string;

  duplicates?: { file: string; similarity: number }[];

  documentationCoverage: number;
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