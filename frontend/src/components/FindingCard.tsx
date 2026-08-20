import { Badge } from "@/components/ui/badge";
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
 * The layout is lifted from the inline block that FileAnalysis has always used,
 * combined with the highlighted fix box SecurityReport used for its
 * `recommendation` — so adopting this loses nothing either page rendered before.
 *
 * Absent fields render nothing. Numeric fields are tested against `undefined`
 * rather than truthiness, so a confidence of 0 still shows.
 */
export function FindingCard({ finding, className }: FindingCardProps) {
  return (
    <div className={cn("flex items-start gap-3 p-3 rounded-lg bg-secondary/20", className)}>
      <SeverityBadge severity={finding.severity} />

      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold">{finding.title}</p>

        {finding.detail && (
          <p className="text-sm text-muted-foreground mt-1">{finding.detail}</p>
        )}

        {finding.whyItMatters && (
          <p className="text-xs text-muted-foreground mt-1.5">
            <span className="font-medium text-foreground/80">Context:</span> {finding.whyItMatters}
          </p>
        )}

        {finding.howToFix && (
          <div className="mt-2 p-3 rounded-lg bg-primary/5 border border-primary/20">
            <p className="text-xs text-muted-foreground mb-1">How to fix</p>
            <p className="text-sm text-primary">{finding.howToFix}</p>
          </div>
        )}

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
      </div>
    </div>
  );
}
