import { Suspense, lazy } from "react";
import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PieChart, Network } from "lucide-react";
import { DependencyGraphView } from "@/components/DependencyGraphView";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";

// F11: recharts is the heaviest thing in the bundle and none of it is needed
// to paint this page's shell or its dependency graph. Deferring it here —
// rather than moving it to a vendor chunk — is what actually shortens time to
// first paint, because this route was already lazily loaded as a whole.
const VisualizationCharts = lazy(
  () => import("@/components/VisualizationCharts")
);

/** Placeholder with the same shape as the chart grid, so the page does not
 *  reflow when the charts arrive. */
function ChartsFallback() {
  return (
    <div className="grid lg:grid-cols-2 gap-6" aria-hidden="true">
      {[0, 1, 2, 3].map((i) => (
        <Card key={i} className="bg-card border-border/50">
          <CardHeader>
            <Skeleton className="h-5 w-48" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-[340px] w-full" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function Visualizations() {
  const { currentReport } = useScan();

  if (!currentReport) {
    return (
      <EmptyState icon={PieChart} title="Run a scan to see visualizations" />
    );
  }

  const { files, summary, dependencies = [] } = currentReport;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Visualization Dashboard</h1>
        <p className="text-muted-foreground mt-1">Charts and graphs for your codebase analysis</p>
      </div>

      {/* Interactive module dependency graph (hover a node to trace its imports) */}
      <Card className="bg-card border-border/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Network className="w-5 h-5 text-primary" />
            Module Dependency Graph
          </CardTitle>
        </CardHeader>
        <CardContent>
          <DependencyGraphView graph={currentReport.dependency_graph} />
        </CardContent>
      </Card>

      <Suspense fallback={<ChartsFallback />}>
        <VisualizationCharts
          files={files}
          summary={summary}
          dependencies={dependencies}
        />
      </Suspense>
    </div>
  );
}
