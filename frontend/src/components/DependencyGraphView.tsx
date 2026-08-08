import { useMemo, useState } from "react";
import { DependencyGraph } from "@/lib/types";

interface DependencyGraphViewProps {
  graph?: DependencyGraph;
  /** Cap on rendered nodes so large repos stay legible (highest-degree kept). */
  maxNodes?: number;
}

/**
 * Lightweight, dependency-free interactive module dependency graph.
 *
 * Nodes (files/modules) are laid out on a circle and links are the import edges
 * from the backend's build_dependency_graph. Hovering a node highlights it, its
 * incident edges, and its direct neighbours (everything else dims), so a
 * reviewer can trace what a file depends on / is depended upon at a glance.
 * Rendered as inline SVG — no graph library, in keeping with the project's
 * zero-new-dependency discipline — and capped to the highest-degree nodes.
 */
export function DependencyGraphView({ graph, maxNodes = 36 }: DependencyGraphViewProps) {
  const [hovered, setHovered] = useState<string | null>(null);

  const layout = useMemo(() => {
    const nodes = graph?.nodes ?? [];
    const links = graph?.links ?? [];
    if (nodes.length === 0) return null;

    // Degree (in + out) drives both node size and which nodes survive the cap.
    const degree = new Map<string, number>();
    for (const l of links) {
      degree.set(l.source, (degree.get(l.source) ?? 0) + 1);
      degree.set(l.target, (degree.get(l.target) ?? 0) + 1);
    }

    const kept = [...nodes]
      .sort((a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0))
      .slice(0, maxNodes);
    const keptIds = new Set(kept.map((n) => n.id));

    const SIZE = 640;
    const R = 250;
    const center = SIZE / 2;
    const pos = new Map<string, { x: number; y: number }>();
    kept.forEach((n, i) => {
      const angle = (2 * Math.PI * i) / kept.length - Math.PI / 2;
      pos.set(n.id, { x: center + R * Math.cos(angle), y: center + R * Math.sin(angle) });
    });

    const edges = links.filter((l) => keptIds.has(l.source) && keptIds.has(l.target));

    const neighbours = new Map<string, Set<string>>();
    for (const id of keptIds) neighbours.set(id, new Set());
    for (const e of edges) {
      neighbours.get(e.source)!.add(e.target);
      neighbours.get(e.target)!.add(e.source);
    }

    const maxDeg = Math.max(1, ...kept.map((n) => degree.get(n.id) ?? 0));
    return { kept, edges, pos, neighbours, degree, maxDeg, SIZE, center, total: nodes.length };
  }, [graph, maxNodes]);

  if (!layout) {
    return (
      <div className="flex items-center justify-center h-[300px] text-muted-foreground text-sm">
        No dependency graph available for this scan.
      </div>
    );
  }

  const { kept, edges, pos, neighbours, degree, maxDeg, SIZE, center, total } = layout;

  const nodeActive = (id: string) =>
    !hovered || hovered === id || (neighbours.get(hovered)?.has(id) ?? false);
  const edgeActive = (s: string, t: string) => !hovered || hovered === s || hovered === t;
  const shortName = (id: string) => id.split("/").pop() || id;

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="w-full max-h-[560px]"
        role="img"
        aria-label="Interactive module dependency graph"
      >
        {/* edges */}
        <g>
          {edges.map((e, i) => {
            const a = pos.get(e.source)!;
            const b = pos.get(e.target)!;
            const active = edgeActive(e.source, e.target);
            return (
              <line
                key={i}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="currentColor"
                strokeWidth={hovered && active ? 1.5 : 0.75}
                className={
                  !active ? "text-border/10" : hovered ? "text-primary/70" : "text-border"
                }
              />
            );
          })}
        </g>

        {/* nodes */}
        {kept.map((n) => {
          const p = pos.get(n.id)!;
          const deg = degree.get(n.id) ?? 0;
          const r = 5 + (deg / maxDeg) * 9;
          const active = nodeActive(n.id);
          const labelRight = p.x >= center;
          return (
            <g
              key={n.id}
              className="cursor-pointer"
              opacity={active ? 1 : 0.25}
              onMouseEnter={() => setHovered(n.id)}
              onMouseLeave={() => setHovered(null)}
            >
              <circle
                cx={p.x}
                cy={p.y}
                r={r}
                className={hovered === n.id ? "fill-primary" : "fill-primary/60"}
              />
              <text
                x={labelRight ? p.x + r + 4 : p.x - r - 4}
                y={p.y + 3}
                textAnchor={labelRight ? "start" : "end"}
                className="fill-muted-foreground"
                fontSize={10}
                fontFamily="'JetBrains Mono', monospace"
              >
                {shortName(n.id)}
              </text>
              <title>{`${n.id} · ${deg} connection${deg === 1 ? "" : "s"}`}</title>
            </g>
          );
        })}
      </svg>

      {total > kept.length && (
        <p className="text-xs text-muted-foreground text-center mt-2">
          Showing the {kept.length} most-connected of {total} modules.
        </p>
      )}
    </div>
  );
}
