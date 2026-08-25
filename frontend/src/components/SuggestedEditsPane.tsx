import { useMemo } from "react";
import { CodeViewer } from "@/components/CodeViewer";
import type { RefactorChange } from "@/lib/types";

interface SuggestedEditsPaneProps {
  improvedCode: string;
  originalCode: string;
  changes: RefactorChange[];
  /** The file's language, so the empty state does not claim checks that never ran. */
  language?: string;
}

/**
 * F4. The pane was labelled "Improved" and, when the engine had nothing to
 * add, rendered the file unchanged with no explanation — which reads as a
 * clean bill of health for a file that had two narrow checks run against it.
 *
 * The engine applies exactly two transforms, so the empty state names both and
 * says what was NOT attempted. Nothing here is applied to the repository.
 *
 * Both transforms go through `ast.parse`, so they only ever run on Python. On
 * any other file they parse nothing and return no changes — which is NOT the
 * same as finding no gaps, and the empty state must not say it is.
 */
export function SuggestedEditsPane({
  improvedCode,
  originalCode,
  changes,
  language,
}: SuggestedEditsPaneProps) {
  const lineCount = useMemo(
    () => (improvedCode ? improvedCode.split("\n").length : 0),
    [improvedCode]
  );

  const highlightedLines = useMemo(() => {
    const lines = new Set<number>();
    for (const change of changes) {
      for (let n = change.line; n < change.line + Math.max(1, change.lineCount); n++) {
        // A record may claim a line past the end of the file — the normalizer
        // bounds the value but cannot know this file's length. Counting one
        // would report more highlights than are visibly marked.
        if (n <= lineCount) lines.add(n);
      }
    }
    return lines;
  }, [changes, lineCount]);

  // The engine rewrote something whenever the improved text differs, even if
  // this scan predates change tracking and carries no per-line records.
  const differs = !!improvedCode && improvedCode !== originalCode;

  if (!differs) {
    const isPython = (language ?? "").toLowerCase() === "python";

    return (
      <div role="status" className="rounded-lg border border-border/50 bg-background p-6 text-sm">
        <p className="font-medium text-foreground">Nothing to suggest here.</p>
        {isPython ? (
          <p className="mt-2 text-muted-foreground">
            Two checks ran against this file: functions and classes with no docstring, and
            functions that never return a value but have no <code>&rarr; None</code> hint.
            This file has neither gap.
          </p>
        ) : (
          <p className="mt-2 text-muted-foreground">
            The only two checks that produce suggestions — missing docstrings, and a missing
            <code> &rarr; None</code> hint — parse Python. This file is
            {language ? ` ${language}` : " not Python"}, so neither ran against it and nothing
            here was examined.
          </p>
        )}
        <p className="mt-2 text-muted-foreground">
          No other transform was attempted — this is not a clean bill of health.
        </p>
      </div>
    );
  }

  const hasLineMarks = highlightedLines.size > 0;

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        {hasLineMarks ? (
          <>
            {highlightedLines.size} changed{" "}
            {highlightedLines.size === 1 ? "line" : "lines"} highlighted.{" "}
          </>
        ) : (
          <>
            This scan was recorded before change tracking, so the edited lines are not marked.{" "}
          </>
        )}
        These edits are suggestions and have not been applied to the repository.
      </p>
      <div className="bg-background border border-border/50 rounded-lg overflow-x-auto overflow-y-auto max-h-[600px] py-4 shadow-inner">
        <CodeViewer
          code={improvedCode}
          highlightedLines={hasLineMarks ? highlightedLines : undefined}
        />
      </div>
    </div>
  );
}
