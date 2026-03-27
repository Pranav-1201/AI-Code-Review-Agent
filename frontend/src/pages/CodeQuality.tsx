import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { ScoreRing } from "@/components/ScoreRing";
import { BarChart3, FileCode } from "lucide-react";

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

  const { files } = currentReport;
  const avgComplexity = Math.round(files.reduce((s, f) => s + f.cyclomaticComplexity, 0) / files.length);
  const avgDocCoverage = Math.round(files.reduce((s, f) => s + f.documentationCoverage, 0) / files.length);
  const longFunctions = files.filter((f) => f.issues.some((i) => i.message.toLowerCase().includes("exceeds")));
  const duplicateFiles = files.filter((f) => f.duplicates && f.duplicates.length > 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Code Quality Insights</h1>
        <p className="text-muted-foreground mt-1">Maintainability metrics and improvement suggestions</p>
      </div>

      <div className="grid md:grid-cols-4 gap-4">
        <Card className="bg-card border-border/50">
          <CardContent className="pt-6 flex flex-col items-center">
            <ScoreRing score={Math.round(currentReport.summary.avg_score)} size={100} />
            <p className="text-xs text-muted-foreground mt-2">Avg Quality Score</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-border/50">
          <CardContent className="pt-6 text-center">
            <p className="text-3xl font-bold font-mono">{avgComplexity}</p>
            <p className="text-xs text-muted-foreground mt-1">Avg Cyclomatic Complexity</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-border/50">
          <CardContent className="pt-6 text-center">
            <p className="text-3xl font-bold font-mono">{avgDocCoverage}%</p>
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

      <Card className="bg-card border-border/50">
        <CardHeader><CardTitle>Complexity by File</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {files
            .sort((a, b) => b.cyclomaticComplexity - a.cyclomaticComplexity)
            .map((file) => (
              <div key={file.path} className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-mono flex items-center gap-2">
                    <FileCode className="w-4 h-4 text-muted-foreground" />
                    {file.name}
                  </span>
                  <span className={`font-mono text-sm ${file.cyclomaticComplexity > 15 ? "text-destructive" : file.cyclomaticComplexity > 10 ? "text-warning" : "text-primary"}`}>
                    {file.cyclomaticComplexity}
                  </span>
                </div>
                <Progress value={Math.min(file.cyclomaticComplexity * 4, 100)} className="h-1.5" />
              </div>
            ))}
        </CardContent>
      </Card>

      {longFunctions.length > 0 && (
        <Card className="bg-card border-border/50">
          <CardHeader><CardTitle>Long Functions Detected</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {longFunctions.map((f) => (
              <div key={f.name} className="p-3 rounded-lg bg-warning/5 border border-warning/20 text-sm">
                <span className="font-mono text-warning">{f.name}</span> — {f.issues.find((i) => i.message.toLowerCase().includes("exceeds"))?.message}
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
