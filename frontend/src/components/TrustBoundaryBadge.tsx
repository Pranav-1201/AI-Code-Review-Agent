import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

interface TrustBoundaryBadgeProps {
  trustBoundary?: string;
  className?: string;
}

/**
 * Surfaces the taint-analysis trust boundary of a security finding so a reviewer
 * can gauge realistic exploitability at a glance — distinguishing a
 * Critical-because-remotely-reachable finding from one only reachable from
 * verified-internal or local-operator input. Values come from the taint analyzer
 * (Phase 3): untrusted_input | operator_input | parameter | internal.
 * "n/a"/undefined means no taint verdict, so nothing is rendered.
 */
const config: Record<string, { label: string; className: string; title: string }> = {
  untrusted_input: {
    label: "Untrusted input",
    className: "bg-destructive/15 text-destructive border-destructive/40",
    title: "Reachable from remote/untrusted input — realistically exploitable.",
  },
  operator_input: {
    label: "Operator input",
    className: "bg-warning/15 text-warning border-warning/30",
    title: "Derives from local operator input (argv/env/stdin) — not remotely reachable.",
  },
  parameter: {
    label: "Unvalidated param",
    className: "bg-secondary text-muted-foreground border-border",
    title: "Flows from an unvalidated parameter; provenance unknown without inter-procedural analysis.",
  },
  internal: {
    label: "Internal",
    className: "bg-primary/10 text-primary border-primary/30",
    title: "Verified internal/constant — not reachable from untrusted input.",
  },
};

export function TrustBoundaryBadge({ trustBoundary, className }: TrustBoundaryBadgeProps) {
  if (!trustBoundary) return null;
  const c = config[trustBoundary];
  if (!c) return null; // "n/a" or unknown → no exploitability signal to surface
  return (
    <Badge variant="outline" title={c.title} className={cn(c.className, "text-[10px]", className)}>
      {c.label}
    </Badge>
  );
}
