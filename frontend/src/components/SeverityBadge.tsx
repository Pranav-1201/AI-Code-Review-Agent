import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Severity } from "@/lib/types";

interface SeverityBadgeProps {
  severity: Severity;
  className?: string;
}

const severityConfig: Record<Severity, string> = {
  // Calmest tier: not reachable from untrusted input (e.g. operator-only code-exec).
  Info: "bg-muted text-muted-foreground border-border",
  Low: "bg-info/15 text-info border-info/30",
  Medium: "bg-warning/15 text-warning border-warning/30",
  High: "bg-destructive/15 text-destructive border-destructive/30",
  Critical: "bg-destructive/20 text-destructive border-destructive/50 font-bold",
};

export function SeverityBadge({ severity, className }: SeverityBadgeProps) {
  return (
    <Badge variant="outline" className={cn(severityConfig[severity], "text-xs", className)}>
      {severity}
    </Badge>
  );
}
