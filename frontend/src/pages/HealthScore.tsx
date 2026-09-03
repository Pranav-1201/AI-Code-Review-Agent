import { useScan } from "@/context/ScanContext";
import { EmptyState } from "@/components/EmptyState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreRing } from "@/components/ScoreRing";
import { Heart, Shield, BarChart3, FileCode, BookOpen } from "lucide-react";
import { Progress } from "@/components/ui/progress";

export default function HealthScore() {
  const { currentReport } = useScan();

  if (!currentReport) {
    return (
      <EmptyState icon={Heart} title="Run a scan to see health score" />
    );
  }

  const { files, summary } = currentReport;

  // Use PRODUCTION files only for sub-score computation
  const prodFiles = files.filter((f) => f.fileType === "production");
  const prodCount = prodFiles.length || 1;

  // Security sub-score: based on production-only security issue count
  const securityScore = summary.security_issues === 0
    ? 100
    : Math.max(0, Math.round(100 - Math.pow(summary.security_issues, 0.7) * 10));

  // Maintainability sub-score: avg quality score of production files
  const maintainabilityScore = Math.round(summary.avg_score);

  // Documentation sub-score: avg doc coverage of production files
  const docScore = summary.avg_documentation_coverage
    ?? Math.round(prodFiles.reduce((s, f) => s + f.documentationCoverage, 0) / prodCount);

  // Simplicity sub-score: based on avg CC of production files. Named for what
  // it measures — this is complexity, not runtime performance, and the backend
  // already calls it simplicity_score.
  const avgCC = summary.avg_cyclomatic_complexity
    ?? Math.round(prodFiles.reduce((s, f) => s + f.cyclomaticComplexity, 0) / prodCount);
  const simplicityScore = Math.max(0, Math.round(100 - Math.min(avgCC * 3, 80)));

  // F14: the weights are the ones the backend applies in health_score. They
  // are shown because the report surfaces both the composite and its largest
  // input (Maintainability is average_quality_score), and 91 alongside 53
  // reads as a contradiction until you can see that 91 carries 35% of it.
  const categories = [
    { name: "Security", score: securityScore, weight: 25, icon: Shield, color: "text-destructive" },
    { name: "Maintainability", score: maintainabilityScore, weight: 35, icon: BarChart3, color: "text-warning" },
    { name: "Documentation", score: docScore, weight: 20, icon: BookOpen, color: "text-info" },
    { name: "Simplicity", score: simplicityScore, weight: 20, icon: FileCode, color: "text-primary" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Repository Health Score</h1>
        <p className="text-muted-foreground mt-1">Overall assessment based on multiple quality dimensions</p>
      </div>

      <div className="flex flex-col items-center gap-3">
        <ScoreRing score={summary.healthScore} size={200} label="Overall Health" />
        <p className="text-sm text-muted-foreground text-center max-w-xl">
          Overall Health is a weighted blend of the four dimensions below — not
          an average of file scores. A repository can hold a high
          Maintainability score and still rate lower overall when documentation
          or complexity drags on it.
        </p>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        {categories.map((cat) => (
          <Card key={cat.name} className="bg-card border-border/50">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3 mb-1">
                <cat.icon className={`w-5 h-5 ${cat.color}`} />
                <span className="font-semibold">{cat.name}</span>
                <span className="ml-auto font-mono font-bold">{cat.score}/100</span>
              </div>
              <div className="flex justify-end mb-2">
                <span className="text-xs text-muted-foreground font-mono">
                  {cat.weight}% of overall
                </span>
              </div>
              <Progress value={cat.score} className="h-2" />
            </CardContent>
          </Card>
        ))}
      </div>

      {/* File breakdown info */}
      {summary.production_files != null && (
        <Card className="bg-card border-border/50">
          <CardContent className="pt-6">
            <div className="flex items-center gap-6 text-sm text-muted-foreground justify-center">
              <span>Scores computed from <strong className="text-foreground">{summary.production_files}</strong> production files</span>
              {summary.test_files != null && summary.test_files > 0 && (
                <span>• <strong className="text-foreground">{summary.test_files}</strong> test files excluded</span>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
