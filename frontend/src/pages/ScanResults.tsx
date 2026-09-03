import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreRing } from "@/components/ScoreRing";
import { SeverityBadge } from "@/components/SeverityBadge";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  FileCode, AlertTriangle, Shield, BarChart3, TrendingDown, Zap,
  CheckCircle2, ChevronDown,
} from "lucide-react";
import { getDisplayName } from "@/lib/response-mapper";
import { EmptyState } from "@/components/EmptyState";
import type { FileAnalysis, Severity } from "@/lib/types";

// Severity ordering used to pick the single headline issue for a file.
const SEVERITY_RANK: Record<Severity, number> = {
  Critical: 5, High: 4, Medium: 3, Low: 2, Info: 1,
};

// The most decision-relevant one-liner for a risky file: its highest-severity
// issue, else its first security finding.
function headlineFinding(file: FileAnalysis): { text: string; severity: Severity } | null {
  const worstIssue = [...file.issues].sort(
    (a, b) => (SEVERITY_RANK[b.severity] ?? 0) - (SEVERITY_RANK[a.severity] ?? 0)
  )[0];
  if (worstIssue) return { text: worstIssue.message, severity: worstIssue.severity };
  const sec = file.security[0];
  if (sec) return { text: sec.description || sec.type, severity: sec.severity };
  return null;
}

// Health verdict — turns the bare number into a human read, colour-matched to
// ScoreRing's thresholds (>=80 healthy, >=60 fair, else needs attention).
function healthVerdict(score: number): { word: string; className: string } {
  if (score >= 90) return { word: "Excellent", className: "text-primary" };
  if (score >= 80) return { word: "Healthy", className: "text-primary" };
  if (score >= 60) return { word: "Fair", className: "text-warning" };
  if (score >= 40) return { word: "Needs attention", className: "text-destructive" };
  return { word: "At risk", className: "text-destructive" };
}

export default function ScanResults() {
  const { currentReport } = useScan();

  if (!currentReport) {
    return (
      <EmptyState icon={AlertTriangle} title="No scan results yet" description="Run a repository scan first" />
    );
  }

  const { summary, files } = currentReport;
  const totalIssues = files.reduce((s, f) => s + f.issues.length, 0);
  const verdict = healthVerdict(summary.healthScore);

  // Risk-weighted production files (security counts double). Top 3 lead the
  // page as the actions to take first; the same ranking's tail lives in the
  // collapsed full list below.
  const riskFiles = [...files]
    .filter((f) => f.fileType === "production" && (f.issues.length > 0 || f.security.length > 0))
    .sort((a, b) => (b.issues.length + b.security.length * 2) - (a.issues.length + a.security.length * 2));
  const topPriorities = riskFiles.slice(0, 3);

  // Most Complex Functions: production code only
  const mostComplexFiles = [...files]
    .filter((f) => f.fileType === "production" && f.cyclomaticComplexity > 0)
    .sort((a, b) => b.cyclomaticComplexity - a.cyclomaticComplexity)
    .slice(0, 5);

  // The full per-file table (all files worth showing) — heavy detail, so it
  // lives behind progressive disclosure.
  const scoredFiles = files
    .filter((f) => f.cyclomaticComplexity > 0 || f.issues.length > 0 || f.score < 100)
    .sort((a, b) => a.score - b.score);

  const metrics = [
    { label: "Files", value: summary.files, icon: FileCode, color: "text-info" },
    { label: "With issues", value: summary.files_with_issues, icon: AlertTriangle, color: "text-warning" },
    { label: "Avg score", value: summary.avg_score.toFixed(1), icon: BarChart3, color: "text-primary" },
    { label: "Security (production)", value: summary.security_issues, icon: Shield, color: "text-destructive" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Scan Results</h1>
        <p className="text-muted-foreground mt-1 font-mono text-sm">{currentReport.repoUrl}</p>
      </div>

      {/* 1. Verdict hero — health is the anchor, everything else is context. */}
      <Card className="bg-card border-border/50">
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row md:items-center gap-6">
            <div className="shrink-0 mx-auto md:mx-0">
              <ScoreRing score={summary.healthScore} size={150} label="Overall Health" />
            </div>

            <div className="flex-1 min-w-0 space-y-4">
              <div>
                <p className="text-sm text-muted-foreground">Project health</p>
                <p className={`text-2xl font-bold ${verdict.className}`}>{verdict.word}</p>
                <p className="text-sm text-muted-foreground mt-1">
                  {summary.files} files analyzed · avg score {summary.avg_score.toFixed(1)} ·{" "}
                  {totalIssues} issue{totalIssues === 1 ? "" : "s"} ·{" "}
                  {summary.security_issues} security finding{summary.security_issues === 1 ? "" : "s"} in production files
                </p>
              </div>

              {/* Key metrics as chips — present but subordinate to the verdict. */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {metrics.map((m) => (
                  <div key={m.label} className="flex items-center gap-2.5 rounded-lg bg-secondary/20 px-3 py-2">
                    <m.icon className={`w-4 h-4 shrink-0 ${m.color} opacity-70`} />
                    <div className="min-w-0">
                      <p className="text-[11px] text-muted-foreground leading-none">{m.label}</p>
                      <p className="text-base font-bold font-mono leading-tight mt-0.5">{m.value}</p>
                    </div>
                  </div>
                ))}
              </div>

              {summary.languages.length > 0 && (
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 pt-1">
                  {summary.languages.slice(0, 6).map((lang) => (
                    <div key={lang.name} className="flex items-center gap-1.5 text-xs">
                      <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: lang.color }} />
                      <span className="text-muted-foreground">{lang.name}</span>
                      <span className="font-mono text-muted-foreground/70">{lang.label}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 2. Top 3 priorities — the actions to take first, above the fold. */}
      <Card className="bg-card border-border/50">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <TrendingDown className="w-5 h-5 text-destructive" />
            Top Priorities
          </CardTitle>
        </CardHeader>
        <CardContent>
          {topPriorities.length > 0 ? (
            <div className="grid gap-3 md:grid-cols-3">
              {topPriorities.map((file, idx) => {
                const headline = headlineFinding(file);
                return (
                  <div key={file.path} className="rounded-lg bg-secondary/20 border border-border/40 p-4 flex flex-col gap-2">
                    <div className="flex items-start gap-2">
                      <span className="font-mono text-sm font-bold text-muted-foreground">{idx + 1}</span>
                      <p className="font-mono text-sm truncate flex-1" title={file.path}>
                        {getDisplayName(file, files)}
                      </p>
                      <span className={`font-mono text-sm font-bold ${file.score >= 80 ? "text-primary" : file.score >= 60 ? "text-warning" : "text-destructive"}`}>
                        {file.score}
                      </span>
                    </div>
                    {headline && (
                      <div className="flex items-start gap-2">
                        <SeverityBadge severity={headline.severity} />
                        <p className="text-xs text-foreground/80 line-clamp-2">{headline.text}</p>
                      </div>
                    )}
                    <div className="flex gap-2 mt-auto pt-1">
                      {file.issues.length > 0 && (
                        <Badge variant="outline" className="text-[10px] text-warning border-warning/30">
                          {file.issues.length} issue{file.issues.length === 1 ? "" : "s"}
                        </Badge>
                      )}
                      {file.security.length > 0 && (
                        <Badge variant="outline" className="text-[10px] text-destructive border-destructive/30">
                          {file.security.length} security
                        </Badge>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-primary bg-secondary/20 rounded-lg p-4">
              <CheckCircle2 className="w-5 h-5 shrink-0" />
              No priority issues — all production files look clean.
            </div>
          )}
        </CardContent>
      </Card>

      {/* 3a. Most complex files — a compact secondary lens (complexity, not risk). */}
      {mostComplexFiles.length > 0 && (
        <Card className="bg-card border-border/50">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Zap className="w-5 h-5 text-warning" />
              Most Complex Files
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {mostComplexFiles.map((file, idx) => (
              <div key={file.path} className="flex items-center gap-3 p-3 rounded-lg bg-secondary/20">
                <span className="font-mono text-sm font-bold text-muted-foreground w-5">{idx + 1}</span>
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-sm truncate" title={file.path}>
                    {getDisplayName(file, files)}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">{file.complexity}</p>
                </div>
                <span className={`font-mono text-sm font-bold ${file.cyclomaticComplexity <= 10 ? "text-primary" : file.cyclomaticComplexity <= 30 ? "text-warning" : "text-destructive"}`}>
                  CC: {file.cyclomaticComplexity}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* 3b. Progressive disclosure — the full per-file table, closed by default. */}
      {scoredFiles.length > 0 && (
        <Card className="bg-card border-border/50">
          <Collapsible>
            <CollapsibleTrigger className="group w-full">
              <CardHeader className="flex-row items-center justify-between hover:bg-secondary/10 rounded-t-lg transition-colors">
                <CardTitle className="text-lg">All File Scores</CardTitle>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span>{scoredFiles.length} files</span>
                  <ChevronDown className="w-4 h-4 transition-transform group-data-[state=open]:rotate-180" />
                </div>
              </CardHeader>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <CardContent className="space-y-3 max-h-[500px] overflow-y-auto">
                {scoredFiles.map((file) => (
                  <div key={file.path} className="flex items-center gap-4 p-3 rounded-lg bg-secondary/20">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="font-mono text-sm truncate" title={file.path}>
                          {getDisplayName(file, files)}
                        </p>
                        {file.fileType === "test" && (
                          <Badge variant="outline" className="text-[9px] px-1.5 py-0 bg-blue-500/10 text-blue-400 border-blue-500/30 shrink-0">TEST</Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        {file.issues.length > 0 && (
                          <Badge variant="outline" className="text-[10px]">{file.issues.length} issues</Badge>
                        )}
                        {file.security.length > 0 && (
                          <Badge variant="outline" className="text-[10px] text-destructive border-destructive/30">
                            {file.security.length} security
                          </Badge>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <Progress value={file.score} className="w-24 h-1.5" />
                      <span className={`font-mono text-sm font-bold ${file.score >= 80 ? "text-primary" : file.score >= 60 ? "text-warning" : "text-destructive"}`}>
                        {file.score}
                      </span>
                    </div>
                  </div>
                ))}
              </CardContent>
            </CollapsibleContent>
          </Collapsible>
        </Card>
      )}
    </div>
  );
}
