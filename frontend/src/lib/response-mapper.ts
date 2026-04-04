import { ScanReport, FileAnalysis, FileIssue, SecurityVulnerability, Dependency } from "./types";

/**
 * Maps the backend API response to our frontend ScanReport type.
 */
export function mapApiResponse(data: any, repoUrl: string): ScanReport {
  const repoName = repoUrl.split("/").pop() || "repository";

  const summary = data.repository_summary || data.summary || {};
  const fileReports: any[] =
    (Array.isArray(data.file_reports) && data.file_reports.length > 0
      ? data.file_reports
      : data.reports) || data.files || [];

  const mappedFiles: FileAnalysis[] = fileReports.map((f: any) => mapFile(f));

  // Production files only (for frontend fallback calculations)
  const prodFiles = mappedFiles.filter((f) => f.fileType === "production");
  const codeFiles = mappedFiles.filter((f) => f.fileType !== "non_code");

  const totalIssues = mappedFiles.reduce((sum, f) => sum + f.issues.length, 0);
  const securityIssues = summary.total_security_issues
    ?? prodFiles.reduce((sum, f) => sum + f.security.length, 0);
  const totalLines = mappedFiles.reduce((sum, f) => sum + f.linesOfCode, 0);

  // Use backend production averages when available
  const avgScore = summary.average_quality_score
    ?? summary.avg_score
    ?? (prodFiles.length > 0
      ? prodFiles.reduce((sum, f) => sum + f.score, 0) / prodFiles.length
      : 0);

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
    c: "hsl(340, 60%, 50%)",
    json: "hsl(120, 40%, 50%)",
    yaml: "hsl(160, 50%, 50%)",
    markdown: "hsl(0, 0%, 60%)",
    shell: "hsl(100, 50%, 45%)",
    sql: "hsl(220, 60%, 55%)",
    toml: "hsl(40, 60%, 50%)",
    config: "hsl(0, 0%, 50%)",
    text: "hsl(0, 0%, 45%)",
    restructuredtext: "hsl(0, 0%, 55%)",
    scss: "hsl(330, 65%, 55%)",
    ruby: "hsl(0, 65%, 55%)",
    php: "hsl(240, 50%, 55%)",
    kotlin: "hsl(275, 60%, 55%)",
    swift: "hsl(10, 80%, 55%)",
    "c#": "hsl(280, 60%, 50%)",
    xml: "hsl(180, 40%, 50%)",
  };

  const languages = Array.from(langMap.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([name, lines]) => ({
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

  const backendDuplicates = data.duplicates || [];

  // --- Use backend-computed health score (production files only) ---
  const avgDocCoverage = summary.avg_documentation_coverage ?? 0;
  const avgCyclomatic = summary.avg_cyclomatic_complexity ?? 0;

  // Prefer backend health_score; fallback to frontend computation from prod files
  const healthScore = summary.health_score ?? (() => {
    const qualityScore = avgScore;
    const secScore = securityIssues === 0 ? 100 : Math.max(0, Math.round(100 - Math.pow(securityIssues, 0.7) * 10));
    const simplicityScore = Math.max(0, Math.round(100 - Math.min(avgCyclomatic * 3, 80)));
    return Math.round(
      0.35 * qualityScore +
      0.25 * secScore +
      0.20 * avgDocCoverage +
      0.20 * simplicityScore
    );
  })();

  return {
    id: `scan-${Date.now()}`,
    repoUrl,
    repoName,
    timestamp: new Date().toISOString(),
    summary: {
      files: summary.files_analyzed || summary.files || mappedFiles.length,
      files_with_issues: summary.files_with_issues || mappedFiles.filter((f) => f.issues.length > 0).length,
      avg_score: Math.round(avgScore * 10) / 10,
      security_issues: securityIssues,
      totalLines: summary.total_lines || summary.lines_of_code || totalLines,
      languages,
      healthScore,
      avg_documentation_coverage: avgDocCoverage,
      avg_cyclomatic_complexity: avgCyclomatic,
      production_files: summary.production_files,
      test_files: summary.test_files,
      maintainability_warnings: summary.maintainability_warnings || [],
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

  if (t === "security" || t.includes("credential") || t.includes("injection") || t.includes("vulnerability")) return "security";
  if (t === "performance" || t.includes("loop") || t.includes("complex")) return "performance";
  if (t === "style" || t.includes("format") || t.includes("naming") || t.includes("convention")) return "style";
  if (t === "logic" || t.includes("error") || t.includes("bug") || t.includes("dead_code")) return "logic";
  return "maintainability";
}


function mapFile(f: any): FileAnalysis {

  const issues: FileIssue[] = (f.issues || []).map((i: any) => {
    const message = i.message || i.description || String(i);
    if (message.toLowerCase().includes("no obvious structural issues")) return null;

    return {
      message,
      severity: mapSeverity(i.severity || "Medium"),
      category: mapCategory(i.type || i.category || ""),
      line: i.line || i.line_number,
    };
  }).filter(Boolean) as FileIssue[];

  const security: SecurityVulnerability[] = (
    f.security || f.security_risks || f.security_vulnerabilities || f.vulnerabilities || []
  ).map((s: any) => {
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

  // Normalize path: always forward slashes
  const rawPath = f.file_path || f.path || f.name || "";
  const filePath = rawPath.replace(/\\/g, "/");
  const fileName = f.file_name || (filePath ? filePath.split("/").pop() : "") || f.name || "unknown";

  // Determine file type from backend classification
  let fileType: "production" | "test" | "non_code" = "production";
  if (f.file_type === "test" || f.is_test === true) {
    fileType = "test";
  } else if (f.file_type === "non_code" || f.is_code === false) {
    fileType = "non_code";
  }

  return {
    name: fileName,
    path: filePath,
    score: f.score || f.quality_score || f.code_quality_score || 50,
    issues,
    security,
    complexity: f.time_complexity || (typeof f.complexity === "string" ? f.complexity : null) || "O(1)",
    cyclomaticComplexity: f.cyclomatic_complexity || f.cyclomaticComplexity || 0,
    maxCyclomaticComplexity: f.max_cyclomatic_complexity || f.maxCyclomaticComplexity || 0,
    linesOfCode: f.lines_of_code || f.linesOfCode || f.lines || f.loc || 0,
    explanation: f.explanation || f.refactor_summary || f.ai_explanation || f.summary || "",
    suggestions: f.suggestions || f.improvements || f.ai_suggestions || [],
    improved_code: f.improved_code || f.refactor_suggestion || f.refactored_code || "",
    original_code: f.original_code || f.content || f.source_code || "",
    patch: f.patch || f.diff || null,
    language: f.language || f.lang || "unknown",
    duplicates: (f.duplicates || []).map((d: any) => ({
      file: d.file || d.file2 || d.path || "",
      similarity: d.similarity || d.score || 0,
    })),
    documentationCoverage: f.documentation_coverage || f.documentationCoverage || f.doc_coverage || 0,
    fileType,
  };
}

function mapSeverity(s: string): "Low" | "Medium" | "High" | "Critical" {
  const normalized = (s || "").toLowerCase();
  if (normalized.includes("critical")) return "Critical";
  if (normalized.includes("high")) return "High";
  if (normalized.includes("medium") || normalized.includes("moderate")) return "Medium";
  return "Low";
}

/**
 * Get a disambiguated display name for a file.
 * If basename is unique, return basename. Otherwise return parent/basename.
 */
export function getDisplayName(file: FileAnalysis, allFiles: FileAnalysis[]): string {
  const basename = file.name;
  const duplicateNames = allFiles.filter((f) => f.name === basename);
  if (duplicateNames.length <= 1) return basename;

  // Show parent directory + basename
  const parts = file.path.split("/");
  if (parts.length >= 2) {
    return parts.slice(-2).join("/");
  }
  return file.path;
}