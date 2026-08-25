import { useMemo } from "react";
import { CodeViewer } from "@/components/CodeViewer";
import type { RefactorChange } from "@/lib/types";

interface SuggestedEditsPaneProps {
  improvedCode: string;
  originalCode: string;
  changes: RefactorChange[];
}

/**
 * F4. The pane was labelled "Improved" and, when the engine had nothing to
 * add, rendered the file unchanged with no explanation — which reads as a
 * clean bill of health for a file that had two narrow checks run against it.
 *
 * The engine applies exactly two transforms, so the empty state names both and
 * says what was NOT attempted. Nothing here is applied to the repository.
 */
export function SuggestedEditsPane({ improvedCode, originalCode, changes }: SuggestedEditsPaneProps) {
  const highlightedLines = useMemo(() => {
    const lines = new Set<number>();
    for (const change of changes) {
      for (let n = change.line; n < change.line + Math.max(1, change.lineCount); n++) {
        lines.add(n);
      }
    }
    return lines;
  }, [changes]);

  const hasEdits = changes.length > 0 && !!improvedCode && improvedCode !== originalCode;

  if (!hasEdits) {
    return (
      <div role="status" className="rounded-lg border border-border/50 bg-background p-6 text-sm">
        <p className="font-medium text-foreground">Nothing to suggest here.</p>
        <p className="mt-2 text-muted-foreground">
          Two checks ran against this file: functions and classes with no docstring, and
          functions that never return a value but have no <code>&rarr; None</code> hint.
          This file has neither gap.
        </p>
        <p className="mt-2 text-muted-foreground">
          No other transform was attempted — this is not a clean bill of health.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        {highlightedLines.size} changed {highlightedLines.size === 1 ? "line" : "lines"} highlighted.
        These edits are suggestions and have not been applied to the repository.
      </p>
      <div className="bg-background border border-border/50 rounded-lg overflow-x-auto overflow-y-auto max-h-[600px] py-4 shadow-inner">
        <CodeViewer code={improvedCode} highlightedLines={highlightedLines} />
      </div>
    </div>
  );
}
