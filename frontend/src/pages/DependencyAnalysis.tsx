import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SeverityBadge } from "@/components/SeverityBadge";
import { Badge } from "@/components/ui/badge";
import { GitBranch, AlertTriangle, CheckCircle } from "lucide-react";

export default function DependencyAnalysis() {
  const { currentReport } = useScan();

  if (!currentReport) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground">
        <GitBranch className="w-12 h-12 mb-4 opacity-30" />
        <p>Run a scan to see dependency analysis</p>
      </div>
    );
  }

  const { dependencies } = currentReport;
  const outdated = dependencies.filter((d) => d.isOutdated);
  const vulnerable = dependencies.filter((d) => d.vulnerabilities.length > 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dependency Analysis</h1>
        <p className="text-muted-foreground mt-1">{dependencies.length} packages analyzed</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card className="bg-card border-border/50">
          <CardContent className="pt-6 text-center">
            <p className="text-3xl font-bold font-mono">{outdated.length}</p>
            <p className="text-xs text-muted-foreground mt-1">Outdated</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-destructive/30">
          <CardContent className="pt-6 text-center">
            <p className="text-3xl font-bold font-mono text-destructive">{vulnerable.length}</p>
            <p className="text-xs text-muted-foreground mt-1">Vulnerable</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-primary/30">
          <CardContent className="pt-6 text-center">
            <p className="text-3xl font-bold font-mono text-primary">{dependencies.filter((d) => !d.isOutdated).length}</p>
            <p className="text-xs text-muted-foreground mt-1">Up to Date</p>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-3">
        {dependencies.map((dep) => (
          <Card key={dep.name} className={`bg-card ${dep.vulnerabilities.length > 0 ? "border-destructive/30" : "border-border/50"}`}>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {dep.vulnerabilities.length > 0 ? (
                    <AlertTriangle className="w-5 h-5 text-destructive" />
                  ) : (
                    <CheckCircle className="w-5 h-5 text-primary" />
                  )}
                  <div>
                    <h3 className="font-mono font-semibold">{dep.name}</h3>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="font-mono text-xs text-muted-foreground">v{dep.version}</span>
                      {dep.isOutdated && (
                        <>
                          <span className="text-muted-foreground">→</span>
                          <span className="font-mono text-xs text-primary">v{dep.latestVersion}</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={dep.riskLevel} />
                  {dep.isOutdated && <Badge variant="outline" className="text-[10px] text-warning border-warning/30">Outdated</Badge>}
                </div>
              </div>
              {dep.vulnerabilities.length > 0 && (
                <div className="mt-3 space-y-1">
                  {dep.vulnerabilities.map((v) => (
                    <div key={v} className="text-xs font-mono text-destructive/80 bg-destructive/5 p-2 rounded">{v}</div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
