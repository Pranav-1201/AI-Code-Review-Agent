import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Download, FileJson, FileText } from "lucide-react";
import { toast } from "sonner";

export default function ExportReport() {
  const { currentReport } = useScan();

  const exportJSON = () => {
    if (!currentReport) return;
    const blob = new Blob([JSON.stringify(currentReport, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${currentReport.repoName}-report.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Report exported as JSON");
  };

  const exportText = () => {
    if (!currentReport) return;
    const lines = [
      `AI Code Review Report — ${currentReport.repoName}`,
      `Repository: ${currentReport.repoUrl}`,
      `Date: ${new Date(currentReport.timestamp).toLocaleString()}`,
      `Health Score: ${currentReport.summary.healthScore}/100`,
      `Files Analyzed: ${currentReport.summary.files}`,
      `Average Score: ${currentReport.summary.avg_score}`,
      `Security Issues: ${currentReport.summary.security_issues}`,
      "",
      "=== FILE ANALYSIS ===",
      "",
      ...currentReport.files.flatMap((f) => [
        `--- ${f.path} (Score: ${f.score}/100) ---`,
        `Complexity: ${f.complexity}`,
        `Issues: ${f.issues.length}`,
        ...f.issues.map((i) => `  [${i.severity}] ${i.message}`),
        `Explanation: ${f.explanation}`,
        "",
      ]),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${currentReport.repoName}-report.txt`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Report exported as Text");
  };

  if (!currentReport) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground">
        <Download className="w-12 h-12 mb-4 opacity-30" />
        <p>Run a scan to export a report</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Export Report</h1>
        <p className="text-muted-foreground mt-1">Download your analysis report</p>
      </div>

      <div className="grid md:grid-cols-2 gap-6 max-w-2xl">
        <Card className="bg-card border-border/50 hover:border-primary/30 transition-colors">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileJson className="w-5 h-5 text-primary" />
              JSON Export
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-4">Full structured data including all metrics, issues, and suggestions.</p>
            <Button onClick={exportJSON} className="w-full gap-2">
              <Download className="w-4 h-4" />
              Download JSON
            </Button>
          </CardContent>
        </Card>

        <Card className="bg-card border-border/50 hover:border-primary/30 transition-colors">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-info" />
              Text Report
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-4">Human-readable summary with all findings and recommendations.</p>
            <Button onClick={exportText} variant="outline" className="w-full gap-2">
              <Download className="w-4 h-4" />
              Download Text
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
