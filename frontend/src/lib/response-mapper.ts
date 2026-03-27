import { ScanReport, FileAnalysis, FileIssue, SecurityVulnerability, Dependency } from "./types";

/**
 * Maps the backend API response to our frontend ScanReport type.
 * Handles variations in the response shape gracefully.
 */
export function mapApiResponse(data: any, repoUrl: string): ScanReport {
  const repoName = repoUrl.split("/").pop() || "repository";

  // Try to extract summary from various possible shapes
  const summary = data.repository_summary || data.summary || {};
  const fileReports: any[] =
  (Array.isArray(data.file_reports) && data.file_reports.length > 0
    ? data.file_reports
    : data.reports) || data.files || [];

  const mappedFiles: FileAnalysis[] = fileReports.map((f: any) => mapFile(f));

  const totalIssues = mappedFiles.reduce((sum, f) => sum + f.issues.length, 0);
  const securityIssues = mappedFiles.reduce((sum, f) => sum + f.security.length, 0);
  const totalLines = mappedFiles.reduce((sum, f) => sum + f.linesOfCode, 0);
  const avgScore = mappedFiles.length > 0
    ? mappedFiles.reduce((sum, f) => sum + f.score, 0) / mappedFiles.length
    : 0;

  // Extract languages from files
  const langMap = new Map<string, number>();
  mappedFiles.forEach((f) => {
    const lang = f.language || "Unknown";
    langMap.set(lang, (langMap.get(lang) || 0) + f.linesOfCode);
  });

  const langColors: Record<string, string> = {
    python: "hsl(210, 80%, 55%)",
    javascript: "hsl(50, 90%, 55%)",
    typescript: "hsl(210, 60%, 50%)",
    html: "hsl(15, 80%, 55%)",
    css: "hsl(262, 80%, 60%)",
    java: "hsl(30, 80%, 50%)",
    go: "hsl(195, 70%, 50%)",
    rust: "hsl(25, 80%, 55%)",
    "c++": "hsl(340, 70%, 55%)",
  };

  const languages = Array.from(langMap.entries()).map(([name, lines]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    percentage: totalLines > 0 ? Math.round((lines / totalLines) * 100) : 0,
    color: langColors[name.toLowerCase()] || "hsl(0, 0%, 60%)",
  }));

  const dependencies: Dependency[] = (data.dependencies || []).map((d: any) => ({
    name: d.name || d.package || "unknown",
    version: d.version || d.current_version || "unknown",
    latestVersion: d.latest_version || d.latestVersion || d.version || "unknown",
    isOutdated: d.is_outdated ?? d.isOutdated ?? false,
    riskLevel: mapSeverity(d.risk_level || d.riskLevel || "Low"),
    vulnerabilities: d.vulnerabilities || [],
  }));

  // Map duplicates from backend data
  const backendDuplicates = data.duplicates || [];

  return {
    id: `scan-${Date.now()}`,
    repoUrl,
    repoName,
    timestamp: new Date().toISOString(),
    summary: {
      files: summary.files_analyzed || summary.files || mappedFiles.length,
      files_with_issues: summary.files_with_issues || mappedFiles.filter((f) => f.issues.length > 0).length,
      avg_score: summary.average_quality_score || summary.avg_score || Math.round(avgScore * 10) / 10,
      security_issues: summary.total_security_issues || summary.security_issues || securityIssues,
      totalLines: summary.total_lines || summary.lines_of_code || totalLines,
      languages,
      healthScore: summary.health_score || summary.healthScore || Math.round(avgScore),
    },
    files: mappedFiles,
    dependencies,
    duplicates: backendDuplicates,
  };
}

/**
 * Map backend issue type to frontend category.
 */
function mapCategory(type: string): "security" | "performance" | "style" | "logic" | "maintainability" {
  const t = (type || "").toLowerCase();

  if (t === "security" || t.includes("credential") || t.includes("injection") || t.includes("vulnerability")) {
    return "security";
  }
  if (t === "performance" || t.includes("loop") || t.includes("complex")) {
    return "performance";
  }
  if (t === "style" || t.includes("format") || t.includes("naming") || t.includes("convention")) {
    return "style";
  }
  if (t === "logic" || t.includes("error") || t.includes("bug") || t.includes("dead_code")) {
    return "logic";
  }

  return "maintainability";
}


function mapFile(f: any): FileAnalysis {

  const issues: FileIssue[] = (f.issues || []).map((i: any) => {
    const message = i.message || i.description || String(i);

    // Filter out placeholder messages
    if (message.toLowerCase().includes("no obvious structural issues")) {
      return null;
    }

    return {
      message,
      severity: mapSeverity(i.severity || "Medium"),
      category: mapCategory(i.type || i.category || ""),
      line: i.line || i.line_number,
    };
  }).filter(Boolean) as FileIssue[];

  const security: SecurityVulnerability[] = (
    f.security ||
    f.security_risks ||
    f.security_vulnerabilities ||
    f.vulnerabilities ||
    []
  ).map((s: any) => {
    // Handle both dict and string formats
    if (typeof s === "string") {
      return {
        type: "Vulnerability",
        severity: "High" as const,
        description: s,
        file: f.path || f.file_path || f.name || "",
        line: undefined,
        recommendation: "",
      };
    }

    return {
      type: s.type || s.name || "Vulnerability",
      severity: mapSeverity(s.severity || "High"),
      description: s.description || s.message || "",
      file: s.file || f.path || f.file_path || f.name || "",
      line: s.line || s.line_number,
      recommendation: s.recommendation || s.fix || "",
    };
  });

  // Use file_path (relative path) for unique identification, file_name for display
  const filePath = f.file_path || f.path || f.name || "";
  const fileName = f.file_name || (filePath ? filePath.split(/[/\\]/).pop() : "") || f.name || "unknown";

  return {
    name: fileName,
    path: filePath,
    score: f.score || f.quality_score || f.code_quality_score || 50,
    issues,
    security,

    // Map time_complexity string (e.g. "O(n)") for display
    complexity: f.time_complexity || (typeof f.complexity === "string" ? f.complexity : null) || "O(1)",

    // Map aggregated cyclomatic complexity from backend
    cyclomaticComplexity: f.cyclomatic_complexity || f.cyclomaticComplexity || 0,

    // FIX: support backend "lines"
    linesOfCode: f.lines_of_code || f.linesOfCode || f.lines || f.loc || 0,

    // FIX: explanation fallback
    explanation: f.explanation || f.refactor_summary || f.ai_explanation || f.summary || "",

    suggestions: f.suggestions || f.improvements || f.ai_suggestions || [],

    // FIX: improved code mapping
    improved_code: f.improved_code || f.refactor_suggestion || f.refactored_code || "",

    // FIX: original code mapping
    original_code: f.original_code || f.content || f.source_code || "",

    patch: f.patch || f.diff || null,

    language: f.language || f.lang || "unknown",

    duplicates: (f.duplicates || []).map((d: any) => ({
      file: d.file || d.file2 || d.path || "",
      similarity: d.similarity || d.score || 0,
    })),

    documentationCoverage:
      f.documentation_coverage ||
      f.documentationCoverage ||
      f.doc_coverage ||
      0,
  };
}

function mapSeverity(s: string): "Low" | "Medium" | "High" | "Critical" {
  const normalized = (s || "").toLowerCase();
  if (normalized.includes("critical")) return "Critical";
  if (normalized.includes("high")) return "High";
  if (normalized.includes("medium") || normalized.includes("moderate")) return "Medium";
  return "Low";
}