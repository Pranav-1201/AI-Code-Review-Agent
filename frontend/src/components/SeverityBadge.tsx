import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

interface SeverityBadgeProps {
  severity: "Low" | "Medium" | "High" | "Critical";
  className?: string;
}

const severityConfig = {
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
