import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { CodeViewer } from "@/components/CodeViewer";
import { cn } from "@/lib/utils";
import type { RefactorChange } from "@/lib/types";

interface WhatChangedPaneProps {
  changes: RefactorChange[];
  patch: string | null;
}

function count(n: number, singular: string, plural: string) {
  return `${n} ${n === 1 ? singular : plural}`;
}

/**
 * F5. This tab used to render the unified diff and nothing else, which asks the
 * reader to reconstruct the intent from +/- lines. The prose is built from the
 * engine's own change records, so it cannot disagree with the highlighting in
 * the pane beside it — both read the same list.
 *
 * The diff is not thrown away; it moves behind a disclosure. A scan recorded
 * before J3 has no change list, and gets told so rather than having prose
 * invented for it by re-parsing the diff.
 */
export function WhatChangedPane({ changes, patch }: WhatChangedPaneProps) {
  const [rawOpen, setRawOpen] = useState(false);

  if (changes.length === 0 && !patch) return null;

  if (changes.length === 0) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted-foreground">
          This scan was recorded before change tracking, so there is no itemised list for it.
          The raw diff it captured is below.
        </p>
        <div className="bg-background border border-border/50 rounded-lg overflow-x-auto overflow-y-auto max-h-[600px] py-4 shadow-inner">
          <CodeViewer code={patch as string} isPatch />
        </div>
      </div>
    );
  }

  const docFunctions = changes.filter((c) => c.kind === "docstring" && c.target === "function");
  const docClasses = changes.filter((c) => c.kind === "docstring" && c.target === "class");
  const hints = changes.filter((c) => c.kind === "return_hint");

  const docTargets = [
    docFunctions.length > 0 ? count(docFunctions.length, "function", "functions") : null,
    docClasses.length > 0 ? count(docClasses.length, "class", "classes") : null,
  ].filter(Boolean);

  return (
    <div className="space-y-4 text-sm">
      {docTargets.length > 0 && (
        <section>
          <p className="font-medium text-foreground">
            Added placeholder docstrings to {docTargets.join(" and ")}.
          </p>
          <p className="mt-1 text-muted-foreground">
            Each of these had no docstring at all. The inserted text names the symbol and
            lists its parameters — it records the gap, it does not describe the behaviour.
          </p>
          <ul className="mt-2 space-y-1 text-muted-foreground">
            {[...docFunctions, ...docClasses].map((c, i) => (
              <li key={`doc-${i}`}>
                <code className="text-foreground">{c.name}</code> ({c.target}) — line {c.line}
              </li>
            ))}
          </ul>
        </section>
      )}

      {hints.length > 0 && (
        <section>
          <p className="font-medium text-foreground">
            Added <code>&rarr; None</code> return hints to {count(hints.length, "function", "functions")}.
          </p>
          <p className="mt-1 text-muted-foreground">
            These functions never return a value, so the hint states a contract the code
            already follows.
          </p>
          <ul className="mt-2 space-y-1 text-muted-foreground">
            {hints.map((c, i) => (
              <li key={`hint-${i}`}>
                <code className="text-foreground">{c.name}</code> — line {c.line}
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="text-xs text-muted-foreground">
        These edits are suggestions and have not been applied to the repository.
      </p>

      {patch && (
        <Collapsible open={rawOpen} onOpenChange={setRawOpen}>
          <CollapsibleTrigger className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground">
            <ChevronDown className={cn("w-4 h-4 transition-transform", rawOpen && "rotate-180")} aria-hidden="true" />
            View raw diff
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="mt-2 bg-background border border-border/50 rounded-lg overflow-x-auto overflow-y-auto max-h-[600px] py-4 shadow-inner">
              <CodeViewer code={patch} isPatch />
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}
