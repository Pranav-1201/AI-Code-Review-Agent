import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Sparkles, FileText } from "lucide-react";

interface ExplanationSourceBadgeProps {
  source?: string;
  className?: string;
}

/**
 * Labels which layer wrote a file's explanation: the Anthropic LLM layer
 * ("llm", grounded in deterministic findings — it paraphrases, it does not
 * detect) or the deterministic template layer ("deterministic"). Lets a reader
 * see how much of the prose is generated vs rule-based. Undefined/unknown →
 * nothing rendered (backward compatible with reports that predate the label).
 */
export function ExplanationSourceBadge({ source, className }: ExplanationSourceBadgeProps) {
  if (source === "llm") {
    return (
      <Badge
        variant="outline"
        title="Explanation written by the Anthropic LLM layer, grounded in deterministic findings."
        className={cn("bg-primary/10 text-primary border-primary/30 text-[10px] gap-1", className)}
      >
        <Sparkles className="w-3 h-3" /> AI-explained
      </Badge>
    );
  }
  if (source === "deterministic") {
    return (
      <Badge
        variant="outline"
        title="Explanation generated from deterministic templates (no LLM)."
        className={cn("bg-secondary text-muted-foreground border-border text-[10px] gap-1", className)}
      >
        <FileText className="w-3 h-3" /> Rule-based
      </Badge>
    );
  }
  return null;
}
