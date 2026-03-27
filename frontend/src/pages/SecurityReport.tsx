import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SeverityBadge } from "@/components/SeverityBadge";
import { Shield, AlertTriangle } from "lucide-react";

export default function SecurityReport() {
  const { currentReport } = useScan();

  if (!currentReport) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground">
        <Shield className="w-12 h-12 mb-4 opacity-30" />
        <p>Run a scan to see security report</p>
      </div>
    );
  }

  const allVulnerabilities = currentReport.files.flatMap((f) => f.security);
  const criticalCount = allVulnerabilities.filter((v) => v.severity === "Critical").length;
  const highCount = allVulnerabilities.filter((v) => v.severity === "High").length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Security Vulnerability Report</h1>
        <p className="text-muted-foreground mt-1">{allVulnerabilities.length} vulnerabilities detected</p>
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
            <Card key={i} className="bg-card border-border/50">
              <CardContent className="pt-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3">
                    <AlertTriangle className={`w-5 h-5 mt-0.5 shrink-0 ${vuln.severity === "Critical" ? "text-destructive" : "text-warning"}`} />
                    <div>
                      <h3 className="font-semibold">{vuln.type}</h3>
                      <p className="text-sm text-muted-foreground mt-1">{vuln.description}</p>
                      <p className="text-xs font-mono text-muted-foreground mt-2">{vuln.file}{vuln.line ? `:${vuln.line}` : ""}</p>
                      <div className="mt-3 p-3 rounded-lg bg-primary/5 border border-primary/20">
                        <p className="text-xs text-muted-foreground mb-1">Recommendation</p>
                        <p className="text-sm text-primary">{vuln.recommendation}</p>
                      </div>
                    </div>
                  </div>
                  <SeverityBadge severity={vuln.severity} />
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
