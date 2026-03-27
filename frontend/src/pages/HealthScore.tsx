import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreRing } from "@/components/ScoreRing";
import { Heart, Shield, BarChart3, FileCode, BookOpen } from "lucide-react";
import { Progress } from "@/components/ui/progress";

export default function HealthScore() {
  const { currentReport } = useScan();

  if (!currentReport) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground">
        <Heart className="w-12 h-12 mb-4 opacity-30" />
        <p>Run a scan to see health score</p>
      </div>
    );
  }

  const { files, summary } = currentReport;
  const securityScore = summary.security_issues === 0
    ? 100
    : Math.max(0, Math.round(100 - Math.log2(summary.security_issues + 1) * 15));
  const maintainabilityScore = Math.round(summary.avg_score);
  const docScore = Math.round(files.reduce((s, f) => s + f.documentationCoverage, 0) / files.length);
  const performanceScore = Math.round(100 - files.reduce((s, f) => s + Math.min(f.cyclomaticComplexity * 3, 50), 0) / files.length);

  const categories = [
    { name: "Security", score: securityScore, icon: Shield, color: "text-destructive" },
    { name: "Maintainability", score: maintainabilityScore, icon: BarChart3, color: "text-warning" },
    { name: "Documentation", score: docScore, icon: BookOpen, color: "text-info" },
    { name: "Performance", score: performanceScore, icon: FileCode, color: "text-primary" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Repository Health Score</h1>
        <p className="text-muted-foreground mt-1">Overall assessment based on multiple quality dimensions</p>
      </div>

      <div className="flex justify-center">
        <ScoreRing score={summary.healthScore} size={200} label="Overall Health" />
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        {categories.map((cat) => (
          <Card key={cat.name} className="bg-card border-border/50">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3 mb-3">
                <cat.icon className={`w-5 h-5 ${cat.color}`} />
                <span className="font-semibold">{cat.name}</span>
                <span className="ml-auto font-mono font-bold">{cat.score}/100</span>
              </div>
              <Progress value={cat.score} className="h-2" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
