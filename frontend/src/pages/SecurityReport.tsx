import { useScan } from "@/context/ScanContext";
import { EmptyState } from "@/components/EmptyState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FindingCard } from "@/components/FindingCard";
import { fromSecurityVulnerability } from "@/lib/findings";
import { Shield } from "lucide-react";

export default function SecurityReport() {
  const { currentReport } = useScan();

  if (!currentReport) {
    return (
      <EmptyState icon={Shield} title="Run a scan to see security report" />
    );
  }

  // The dashboard tile counts production files only, because the backend's
  // total_security_issues does (repository_review_engine.py:512-514) and it
  // feeds health_score. This page matches that scope so the two numbers agree,
  // and accounts for what it excluded rather than hiding it.
  const productionFiles = currentReport.files.filter((f) => f.fileType === "production");
  const allVulnerabilities = productionFiles.flatMap((f) => f.security);
  const excludedCount = currentReport.files
    .filter((f) => f.fileType !== "production")
    .reduce((n, f) => n + f.security.length, 0);
  const criticalCount = allVulnerabilities.filter((v) => v.severity === "Critical").length;
  const highCount = allVulnerabilities.filter((v) => v.severity === "High").length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Security Vulnerability Report</h1>
        <p className="text-muted-foreground mt-1">
          {allVulnerabilities.length} finding{allVulnerabilities.length === 1 ? "" : "s"} in production files
        </p>
        {excludedCount > 0 && (
          <p className="text-xs text-muted-foreground/70 mt-1">
            {excludedCount} further finding{excludedCount === 1 ? "" : "s"} in test/non-code files, excluded from the score
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="bg-card border-destructive/30">
          <CardContent className="pt-6 text-center">
            <p className="text-3xl font-bold font-mono text-destructive">{criticalCount}</p>
            <p className="text-xs text-muted-foreground mt-1">Critical</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-destructive/20">
          <CardContent className="pt-6 text-center">
            <p className="text-3xl font-bold font-mono text-destructive/80">{highCount}</p>
            <p className="text-xs text-muted-foreground mt-1">High</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-warning/20">
          <CardContent className="pt-6 text-center">
            <p className="text-3xl font-bold font-mono text-warning">{allVulnerabilities.filter((v) => v.severity === "Medium").length}</p>
            <p className="text-xs text-muted-foreground mt-1">Medium</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-info/20">
          <CardContent className="pt-6 text-center">
            <p className="text-3xl font-bold font-mono text-info">{allVulnerabilities.filter((v) => v.severity === "Low").length}</p>
            <p className="text-xs text-muted-foreground mt-1">Low</p>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4">
        {allVulnerabilities.length === 0 ? (
          <Card className="bg-card border-primary/30">
            <CardContent className="pt-6 text-center">
              <Shield className="w-12 h-12 text-primary mx-auto mb-2" />
              <p className="text-primary font-medium">No security vulnerabilities detected</p>
            </CardContent>
          </Card>
        ) : (
          allVulnerabilities.map((vuln, i) => (
            <FindingCard key={i} finding={fromSecurityVulnerability(vuln)} />
          ))
        )}
      </div>
    </div>
  );
}
