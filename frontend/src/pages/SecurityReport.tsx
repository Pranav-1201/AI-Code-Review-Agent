import { useScan } from "@/context/ScanContext";
import { EmptyState } from "@/components/EmptyState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FindingCard } from "@/components/FindingCard";
import { fromSecurityVulnerability } from "@/lib/findings";
import { cn } from "@/lib/utils";
import type { Severity } from "@/lib/types";
import { Shield } from "lucide-react";

// Five, not four. `Severity` has five values and `types.ts` records why Info
// is distinct: a code-exec sink that taint proved is reachable only from
// local operator input. The page used to render four tiles, so an Info
// finding showed in the list below while no tile counted it and the tiles
// did not sum to the headline.
const SEVERITY_ORDER: Severity[] = ["Critical", "High", "Medium", "Low", "Info"];

const TIER_STYLES: Record<Severity, { border: string; text: string }> = {
  Critical: { border: "border-destructive/30", text: "text-destructive" },
  High: { border: "border-destructive/20", text: "text-destructive/80" },
  Medium: { border: "border-warning/20", text: "text-warning" },
  Low: { border: "border-info/20", text: "text-info" },
  Info: { border: "border-border", text: "text-muted-foreground" },
};

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

  const groups = SEVERITY_ORDER.map((severity) => ({
    severity,
    id: `severity-${severity.toLowerCase()}`,
    findings: allVulnerabilities.filter((v) => v.severity === severity),
  }));

  // Scrolling alone moves the viewport and leaves a keyboard or screen-reader
  // user where they were. Moving focus is what makes a tier a navigation
  // control rather than a decoration.
  const jumpTo = (id: string) => {
    const target = document.getElementById(id);
    if (!target) return;

    const reduced =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    target.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
    // preventScroll: true — focus() defaults to its own instant scroll,
    // which would jump the viewport right after the smooth scroll above and
    // defeat the prefers-reduced-motion branch entirely.
    target.focus({ preventScroll: true });
  };

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

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {groups.map(({ severity, id, findings }) => {
          const styles = TIER_STYLES[severity];
          const inner = (
            <>
              <p className={cn("text-3xl font-bold font-mono", styles.text)}>{findings.length}</p>
              <p className="text-xs text-muted-foreground mt-1">{severity}</p>
            </>
          );

          // A tier with nothing behind it is not a control: activating it
          // would jump to a group that renders nothing.
          if (findings.length === 0) {
            return (
              <Card key={severity} className={cn("bg-card", styles.border)}>
                <CardContent className="pt-6 text-center">{inner}</CardContent>
              </Card>
            );
          }

          return (
            <Card key={severity} className={cn("bg-card", styles.border)}>
              <CardContent className="p-0">
                <button
                  type="button"
                  onClick={() => jumpTo(id)}
                  aria-label={`${findings.length} ${severity} — jump to findings`}
                  className="w-full pt-6 pb-6 px-6 text-center rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background hover:bg-secondary/20 transition-colors"
                >
                  {inner}
                </button>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="space-y-8">
        {allVulnerabilities.length === 0 ? (
          <Card className="bg-card border-primary/30">
            <CardContent className="pt-6 text-center">
              <Shield className="w-12 h-12 text-primary mx-auto mb-2" />
              {/* Scoped to match the headline above. An unqualified "none detected"
                  would contradict the "N further findings in test/non-code files"
                  line this same page renders when excludedCount > 0. */}
              <p className="text-primary font-medium">No security findings in production files</p>
            </CardContent>
          </Card>
        ) : (
          groups
            .filter((g) => g.findings.length > 0)
            .map(({ severity, id, findings }) => (
              <section key={severity} className="space-y-4">
                <h2
                  id={id}
                  tabIndex={-1}
                  className="text-lg font-semibold tracking-tight scroll-mt-24 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
                >
                  {severity} — {findings.length} finding{findings.length === 1 ? "" : "s"}
                </h2>
                {findings.map((vuln, i) => (
                  <FindingCard key={`${severity}-${i}`} finding={fromSecurityVulnerability(vuln)} />
                ))}
              </section>
            ))
        )}
      </div>
    </div>
  );
}
