import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { ScoreRing } from "@/components/ScoreRing";
import { Badge } from "@/components/ui/badge";
import { BarChart3, FileCode, Zap, AlertTriangle } from "lucide-react";
import { getDisplayName } from "@/lib/response-mapper";

export default function CodeQuality() {
  const { currentReport } = useScan();

  if (!currentReport) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground">
        <BarChart3 className="w-12 h-12 mb-4 opacity-30" />
        <p>Run a scan to see code quality insights</p>
      </div>
    );
  }

  const { files, summary } = currentReport;

  // Production files only for metrics
  const prodFiles = files.filter((f) => f.fileType === "production");

  // Use backend-computed averages (production only)
  const avgComplexity = summary.avg_cyclomatic_complexity
    ?? (prodFiles.length > 0
      ? Math.round(prodFiles.reduce((s, f) => s + f.cyclomaticComplexity, 0) / prodFiles.length)
      : 0);

  const maxComplexity = prodFiles.length > 0
    ? Math.max(...prodFiles.map(f => f.cyclomaticComplexity))
    : 0;

  const avgDocCoverage = summary.avg_documentation_coverage
    ?? (prodFiles.length > 0
      ? Math.round(prodFiles.reduce((s, f) => s + f.documentationCoverage, 0) / prodFiles.length)
      : 0);

  const duplicateFiles = files.filter((f) => f.duplicates && f.duplicates.length > 0);

  // Maintainability warnings from backend, or fallback detection
  const maintainabilityWarnings = summary.maintainability_warnings && summary.maintainability_warnings.length > 0
    ? summary.maintainability_warnings
    : [
        // Fallback: detect long production files
        ...prodFiles
          .filter((f) => f.linesOfCode > 300)
          .map((f) => ({
            file: f.path,
            type: "long_file",
            message: `File is ${f.linesOfCode} lines long — consider splitting into smaller modules`,
            severity: "medium",
          })),
        // Fallback: detect complex production functions
        ...prodFiles
          .filter((f) => f.maxCyclomaticComplexity > 10)
          .map((f) => ({
            file: f.path,
            type: "complex_function",
            message: `Contains function(s) with cyclomatic complexity ${f.maxCyclomaticComplexity} — consider refactoring`,
            severity: f.maxCyclomaticComplexity > 20 ? "high" : "medium",
          })),
      ];

  const getComplexityColor = (cc: number) => {
    if (cc <= 10) return "text-primary";
    if (cc <= 30) return "text-warning";
    return "text-destructive";
  };

  const getComplexityProgressBar = (cc: number) => {
    if (cc <= 10) return "bg-primary";
    if (cc <= 30) return "bg-warning";
    return "bg-destructive";
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Code Quality Insights</h1>
        <p className="text-muted-foreground mt-1">Maintainability metrics and improvement suggestions</p>
      </div>

      <div className="grid md:grid-cols-4 gap-4">
        <Card className="bg-card border-border/50">
          <CardContent className="pt-6 flex flex-col items-center">
            <ScoreRing score={Math.round(summary.avg_score)} size={100} />
            <p className="text-xs text-muted-foreground mt-2">Avg Quality Score</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-border/50">
          <CardContent className="pt-6 text-center">
            <div className="flex items-center justify-center gap-3">
              <div>
                <p className={`text-3xl font-bold font-mono ${getComplexityColor(avgComplexity)}`}>{avgComplexity}</p>
                <p className="text-xs text-muted-foreground mt-1">Avg CC</p>
              </div>
              <div className="w-px h-10 bg-border/50"></div>
              <div>
                <p className={`text-3xl font-bold font-mono ${getComplexityColor(maxComplexity)}`}>{maxComplexity}</p>
                <p className="text-xs text-muted-foreground mt-1">Max CC</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-card border-border/50">
          <CardContent className="pt-6 text-center">
            <p className="text-3xl font-bold font-mono text-info">{avgDocCoverage}%</p>
            <p className="text-xs text-muted-foreground mt-1">Avg Doc Coverage</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-border/50">
          <CardContent className="pt-6 text-center">
            <p className="text-3xl font-bold font-mono">{duplicateFiles.length}</p>
            <p className="text-xs text-muted-foreground mt-1">Files with Duplicates</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <Card className="bg-card border-border/50">
          <CardHeader><CardTitle className="flex items-center gap-2"><Zap className="w-5 h-5 text-warning" /> Most Complex Files</CardTitle></CardHeader>
          <CardContent className="space-y-4 max-h-[500px] overflow-y-auto pr-2">
            {prodFiles
              .filter(f => f.cyclomaticComplexity > 0)
              .sort((a, b) => b.cyclomaticComplexity - a.cyclomaticComplexity)
              .slice(0, 20)
              .map((file) => (
                <div key={file.path} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-mono flex items-center gap-2 truncate" title={file.path}>
                      <FileCode className="w-4 h-4 text-muted-foreground shrink-0" />
                      <span className="truncate">{getDisplayName(file, files)}</span>
                    </span>
                    <span className={`font-mono text-sm font-bold ${getComplexityColor(file.cyclomaticComplexity)} shrink-0 pl-2`}>
                      CC: {file.cyclomaticComplexity}
                    </span>
                  </div>
                  {/* Custom progress bar to support color change */}
                  <div className="h-1.5 w-full bg-secondary/50 rounded-full overflow-hidden">
                    <div
                      className={`h-full ${getComplexityProgressBar(file.cyclomaticComplexity)} transition-all`}
                      style={{ width: `${Math.min(file.cyclomaticComplexity * 5, 100)}%` }}
                    />
                  </div>
                </div>
              ))}
          </CardContent>
        </Card>

        {maintainabilityWarnings.length > 0 ? (
          <Card className="bg-card border-border/50">
            <CardHeader><CardTitle className="flex items-center gap-2"><AlertTriangle className="w-5 h-5 text-warning" /> Maintainability</CardTitle></CardHeader>
            <CardContent className="space-y-2 max-h-[500px] overflow-y-auto">
              {maintainabilityWarnings.map((w, idx) => (
                <div key={`${w.file}-${idx}`} className="p-3 rounded-lg bg-warning/5 border border-warning/20 text-sm">
                  <span className="font-mono text-warning font-semibold truncate block" title={w.file}>
                    {w.file.split("/").pop()}
                  </span>
                  <div className="mt-1 text-muted-foreground flex items-center gap-2">
                    <Badge variant="outline" className={`text-[9px] shrink-0 ${w.severity === "high" ? "text-destructive border-destructive/30" : "text-warning border-warning/30"}`}>
                      {w.type === "long_file" ? "Long File" : "High Complexity"}
                    </Badge>
                    <span>{w.message}</span>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        ) : (
          <Card className="bg-card border-border/50">
            <CardHeader><CardTitle>Maintainability</CardTitle></CardHeader>
            <CardContent>
              <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                <BarChart3 className="w-8 h-8 mb-2 opacity-50" />
                <p>No maintainability issues detected.</p>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
