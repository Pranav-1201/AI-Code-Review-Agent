import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreRing } from "@/components/ScoreRing";
import { SeverityBadge } from "@/components/SeverityBadge";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { FileCode, AlertTriangle, Shield, BarChart3, TrendingDown, Zap } from "lucide-react";
import { getDisplayName } from "@/lib/response-mapper";

export default function ScanResults() {
  const { currentReport } = useScan();

  if (!currentReport) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground">
        <AlertTriangle className="w-12 h-12 mb-4 opacity-30" />
        <p className="text-lg">No scan results yet</p>
        <p className="text-sm">Run a repository scan first</p>
      </div>
    );
  }

  const { summary, files } = currentReport;

  // Top Risk Files: production code only (test files excluded from risk ranking)
  const topRiskFiles = [...files]
    .filter((f) => f.fileType === "production" && (f.issues.length > 0 || f.security.length > 0))
    .sort((a, b) => (b.issues.length + b.security.length * 2) - (a.issues.length + a.security.length * 2))
    .slice(0, 5);

  // Most Complex Functions: production code only
  const mostComplexFiles = [...files]
    .filter((f) => f.fileType === "production" && f.cyclomaticComplexity > 0)
    .sort((a, b) => b.cyclomaticComplexity - a.cyclomaticComplexity)
    .slice(0, 5);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Scan Results</h1>
        <p className="text-muted-foreground mt-1 font-mono text-sm">{currentReport.repoUrl}</p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Files Analyzed", value: summary.files, icon: FileCode, color: "text-info" },
          { label: "Files with Issues", value: summary.files_with_issues, icon: AlertTriangle, color: "text-warning" },
          { label: "Avg Score", value: summary.avg_score.toFixed(1), icon: BarChart3, color: "text-primary" },
          { label: "Security Issues", value: summary.security_issues, icon: Shield, color: "text-destructive" },
        ].map((stat) => (
          <Card key={stat.label} className="bg-card border-border/50">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-muted-foreground">{stat.label}</p>
                  <p className="text-2xl font-bold font-mono mt-1">{stat.value}</p>
                </div>
                <stat.icon className={`w-8 h-8 ${stat.color} opacity-50`} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* File Scores */}
        <Card className="lg:col-span-2 bg-card border-border/50">
          <CardHeader>
            <CardTitle className="text-lg">File Scores</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 max-h-[500px] overflow-y-auto">
            {files
              .filter((f) => f.cyclomaticComplexity > 0 || f.issues.length > 0 || f.score < 100)
              .sort((a, b) => a.score - b.score)
              .map((file) => (
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
                      <SeverityBadge severity="Critical" />
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
        </Card>

        {/* Health Score */}
        <Card className="bg-card border-border/50">
          <CardHeader>
            <CardTitle className="text-lg">Health Score</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col items-center">
            <ScoreRing score={summary.healthScore} size={160} label="Overall Health" />
            <div className="mt-4 w-full space-y-2">
              {summary.languages.slice(0, 6).map((lang) => (
                <div key={lang.name} className="flex items-center gap-2 text-sm">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: lang.color }} />
                  <span className="flex-1">{lang.name}</span>
                  <span className="font-mono text-muted-foreground">{lang.percentage}%</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Top Risk Files + Most Complex */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Top Risk Files */}
        {topRiskFiles.length > 0 && (
          <Card className="bg-card border-border/50">
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <TrendingDown className="w-5 h-5 text-destructive" />
                Top Risk Files
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {topRiskFiles.map((file, idx) => (
                <div key={file.path} className="flex items-center gap-3 p-3 rounded-lg bg-secondary/20">
                  <span className="font-mono text-sm font-bold text-muted-foreground w-5">{idx + 1}</span>
                  <div className="flex-1 min-w-0">
                    <p className="font-mono text-sm truncate" title={file.path}>
                      {getDisplayName(file, files)}
                    </p>
                    <div className="flex gap-2 mt-1">
                      {file.issues.length > 0 && (
                        <Badge variant="outline" className="text-[10px] text-warning border-warning/30">
                          {file.issues.length} issues
                        </Badge>
                      )}
                      {file.security.length > 0 && (
                        <Badge variant="outline" className="text-[10px] text-destructive border-destructive/30">
                          {file.security.length} security
                        </Badge>
                      )}
                    </div>
                  </div>
                  <span className={`font-mono text-sm font-bold ${file.score >= 80 ? "text-primary" : file.score >= 60 ? "text-warning" : "text-destructive"}`}>
                    {file.score}
                  </span>
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Most Complex */}
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
      </div>
    </div>
  );
}
