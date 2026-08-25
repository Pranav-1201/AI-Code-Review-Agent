import { cn } from "@/lib/utils";

interface CodeViewerProps {
  code: string;
  /** Colour the content as a unified diff rather than as source. */
  isPatch?: boolean;
  /**
   * 1-based line numbers to mark as changed. Ignored when `isPatch` is set —
   * a diff already carries its own +/- signal and stacking a second one on top
   * would say the same thing twice.
   */
  highlightedLines?: ReadonlySet<number>;
}

/**
 * Renders code with line numbers, in one of three modes: plain source, a
 * unified diff coloured by leading character, or source with specific lines
 * marked as changed.
 *
 * Lived inline in FileAnalysis until J3, when a second pane needed it.
 */
export function CodeViewer({ code, isPatch = false, highlightedLines }: CodeViewerProps) {
  if (!code) return <span>Not available</span>;

  const lines = code.split("\n");
  const marking = !isPatch && highlightedLines !== undefined;

  return (
    <div className="flex flex-col font-mono text-[13px] leading-snug w-full min-w-max">
      {lines.map((line, i) => {
        const lineNumber = i + 1;
        const isChanged = marking && highlightedLines.has(lineNumber);

        let bgColor = "transparent";
        let textColor = "text-foreground/80";

        if (isPatch) {
          if (line.startsWith("+") && !line.startsWith("+++")) {
            bgColor = "bg-primary/20";
            textColor = "text-primary border-l-2 border-primary";
          } else if (line.startsWith("-") && !line.startsWith("---")) {
            bgColor = "bg-destructive/20";
            textColor = "text-destructive border-l-2 border-destructive";
          } else if (line.startsWith("@@")) {
            textColor = "text-info font-bold";
            bgColor = "bg-info/10";
          } else {
            textColor = "text-muted-foreground";
          }
        } else if (isChanged) {
          bgColor = "bg-primary/15";
          textColor = "text-foreground";
        }

        return (
          <div
            key={i}
            data-changed={isChanged ? "true" : undefined}
            className={cn("flex px-2 hover:bg-white/5", bgColor, isChanged && "border-l-2 border-primary")}
          >
            {marking && (
              <span aria-hidden="true" className="w-3 shrink-0 select-none text-primary">
                {isChanged ? "+" : " "}
              </span>
            )}
            <span className="w-10 shrink-0 text-muted-foreground/50 select-none text-right pr-4 border-r border-border/50 mr-4">
              {lineNumber}
            </span>
            {isChanged && <span className="sr-only">Changed line. </span>}
            <span className={`whitespace-pre ${textColor}`}>{line || " "}</span>
          </div>
        );
      })}
    </div>
  );
}
