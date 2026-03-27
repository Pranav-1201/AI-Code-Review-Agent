import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreRing } from "@/components/ScoreRing";
import { SeverityBadge } from "@/components/SeverityBadge";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { FileCode, AlertTriangle, Shield, BarChart3 } from "lucide-react";

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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Scan Results</h1>
        <p className="text-muted-foreground mt-1 font-mono text-sm">{currentReport.repoUrl}</p>
      </div>

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
        <Card className="lg:col-span-2 bg-card border-border/50">
          <CardHeader>
            <CardTitle className="text-lg">File Scores</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {files.map((file) => (
              <div key={file.path} className="flex items-center gap-4 p-3 rounded-lg bg-secondary/20">
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-sm truncate">{file.name}</p>
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

        <Card className="bg-card border-border/50">
          <CardHeader>
            <CardTitle className="text-lg">Health Score</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col items-center">
            <ScoreRing score={summary.healthScore} size={160} label="Overall Health" />
            <div className="mt-4 w-full space-y-2">
              {summary.languages.map((lang) => (
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
    </div>
  );
}
