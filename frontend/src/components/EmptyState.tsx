import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  /** Illustrative icon; rendered decoratively (aria-hidden). */
  icon: LucideIcon;
  title: string;
  description?: string;
  className?: string;
  /** Optional action(s), e.g. a button. */
  children?: ReactNode;
}

/**
 * Shared "nothing to show yet" placeholder used by the result pages when no
 * scan has been run. Extracted from ~12 near-identical copies so the layout,
 * spacing, and accessibility semantics stay consistent. `role="status"` lets
 * assistive tech announce the placeholder; the icon is decorative.
 */
export function EmptyState({ icon: Icon, title, description, className, children }: EmptyStateProps) {
  return (
    <div
      role="status"
      className={cn(
        "flex flex-col items-center justify-center h-[60vh] text-center text-muted-foreground",
        className
      )}
    >
      <Icon className="w-12 h-12 mb-4 opacity-30" aria-hidden="true" />
      <p className="text-lg">{title}</p>
      {description && <p className="text-sm mt-1">{description}</p>}
      {children}
    </div>
  );
}
