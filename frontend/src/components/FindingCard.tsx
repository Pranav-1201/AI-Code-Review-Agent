import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { SeverityBadge } from "@/components/SeverityBadge";
import { TrustBoundaryBadge } from "@/components/TrustBoundaryBadge";
import type { FindingView } from "@/lib/findings";
import { cn } from "@/lib/utils";

interface FindingCardProps {
  finding: FindingView;
  className?: string;
}

/**
 * One finding, explained the same way everywhere.
 *
 * Collapsed by default (J2/F9): a real report carries hundreds of findings and
 * rendering every explanation at once produced a wall nobody read. What stays
 * visible while closed is what you triage on — severity, what it is, which
 * file and line, trust boundary, confidence. The explanation is one click away.
 *
 * A finding with nothing to expand renders no control at all, so the list never
 * offers a button that does nothing.
 *
 * Absent fields render nothing. Numeric fields are tested against `undefined`
 * rather than truthiness, so a confidence of 0 still shows.
 */
export function FindingCard({ finding, className }: FindingCardProps) {
  const [open, setOpen] = useState(false);

  const hasDetail = Boolean(
    finding.detail || finding.whyItMatters || finding.howToFix || finding.snippet
  );

  const badges = (
    <div className="flex gap-2 mt-2 flex-wrap">
      {finding.fileName && (
        <Badge variant="outline" className="text-[10px] font-mono">{finding.fileName}</Badge>
      )}
      {finding.line !== undefined && (
        <Badge variant="outline" className="text-[10px] font-mono">Line {finding.line}</Badge>
      )}
      {finding.category && (
        <Badge variant="outline" className="text-[10px]">{finding.category}</Badge>
      )}
      <TrustBoundaryBadge trustBoundary={finding.trustBoundary} />
      {finding.confidence !== undefined && (
        <Badge variant="outline" className="text-[10px] border-primary/20 text-primary/80">
          {(finding.confidence * 100).toFixed(0)}% Match
        </Badge>
      )}
    </div>
  );

  const body = (
    <>
      {finding.detail && (
        <p className="text-sm text-muted-foreground mt-1">{finding.detail}</p>
      )}

      {finding.whyItMatters && (
        <p className="text-xs text-muted-foreground mt-1.5">
          <span className="font-medium text-foreground/80">Context:</span> {finding.whyItMatters}
        </p>
      )}

      {finding.snippet && (
        <pre className="mt-2 p-3 rounded-lg bg-background/60 border border-border overflow-x-auto text-xs font-mono leading-relaxed">
          <code>{finding.snippet}</code>
        </pre>
      )}

      {finding.howToFix && (
        <div className="mt-2 p-3 rounded-lg bg-primary/5 border border-primary/20">
          <p className="text-xs text-muted-foreground mb-1">How to fix</p>
          <p className="text-sm text-primary">{finding.howToFix}</p>
        </div>
      )}
    </>
  );

  if (!hasDetail) {
    return (
      <div className={cn("flex items-start gap-3 p-3 rounded-lg bg-secondary/20", className)}>
        <SeverityBadge severity={finding.severity} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold">{finding.title}</p>
          {badges}
        </div>
      </div>
    );
  }

  return (
    <div className={cn("flex items-start gap-3 p-3 rounded-lg bg-secondary/20", className)}>
      <SeverityBadge severity={finding.severity} />

      <div className="flex-1 min-w-0">
        <Collapsible open={open} onOpenChange={setOpen}>
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex w-full items-start gap-2 text-left rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
            >
              <span className="text-sm font-semibold flex-1">{finding.title}</span>
              <ChevronDown
                aria-hidden="true"
                className={cn(
                  "w-4 h-4 shrink-0 mt-0.5 text-muted-foreground transition-transform",
                  open && "rotate-180"
                )}
              />
            </button>
          </CollapsibleTrigger>

          <CollapsibleContent>{body}</CollapsibleContent>
        </Collapsible>

        {badges}
      </div>
    </div>
  );
}
