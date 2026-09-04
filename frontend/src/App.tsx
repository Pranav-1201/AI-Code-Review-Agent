import { lazy, Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import * as TooltipProvider from "@radix-ui/react-tooltip";
import { Loader2 } from "lucide-react";
import { ScanProvider } from "@/context/ScanContext";
import { ThemeProvider } from "@/context/ThemeContext";
import { DashboardLayout } from "@/components/DashboardLayout";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { RouteHead } from "@/components/RouteHead";
import { ROUTES } from "@/lib/routes";

// The landing route stays eager: it is the first paint, and a loading
// fallback there would be a flash of nothing on every cold visit.
import RepositoryScanner from "@/pages/RepositoryScanner";

// Everything else is lazy. These pages pull recharts, react-markdown and the
// dependency-graph renderer, all of which used to sit in the entry chunk.
// Keyed by path so App.tsx and routes.ts cannot disagree about which
// component belongs where. The lazy import() calls have to live here rather
// than in routes.ts, because vite.config.ts imports that file in Node to build
// the sitemap and it must therefore stay free of any import at all.
const PAGES: Record<string, ReturnType<typeof lazy>> = {
  "/results": lazy(() => import("@/pages/ScanResults")),
  "/overview": lazy(() => import("@/pages/RepositoryOverview")),
  "/file-analysis": lazy(() => import("@/pages/FileAnalysis")),
  "/security": lazy(() => import("@/pages/SecurityReport")),
  "/quality": lazy(() => import("@/pages/CodeQuality")),
  "/dependencies": lazy(() => import("@/pages/DependencyAnalysis")),
  "/duplicates": lazy(() => import("@/pages/DuplicateDetection")),
  "/ai-suggestions": lazy(() => import("@/pages/AISuggestions")),
  "/health": lazy(() => import("@/pages/HealthScore")),
  "/issues": lazy(() => import("@/pages/IssueExplorer")),
  "/visualizations": lazy(() => import("@/pages/Visualizations")),
  "/history": lazy(() => import("@/pages/ScanHistory")),
  "/export": lazy(() => import("@/pages/ExportReport")),
  "/settings": lazy(() => import("@/pages/Settings")),
};

const NotFound = lazy(() => import("@/pages/NotFound"));

const queryClient = new QueryClient();

function RouteFallback() {
  return (
    // data-testid is a test hook: role="status" alone is not specific enough to
    // wait on, because EmptyState carries it too, which makes a page that
    // legitimately renders empty indistinguishable from a chunk that never
    // loaded.
    <div
      className="flex items-center justify-center py-24"
      role="status"
      aria-live="polite"
      data-testid="route-fallback"
    >
      <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" aria-hidden="true" />
      <span className="sr-only">Loading page</span>
    </div>
  );
}

const App = () => (
  <ThemeProvider>
    <QueryClientProvider client={queryClient}>
    <TooltipProvider.Provider>
      <Toaster richColors position="top-right" />
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ScanProvider>
          {/* One head manager for every route, rather than a call in each of
              the 15 pages — the metadata already lives centrally in routes.ts,
              and 15 call sites would be 15 chances to forget one. */}
          <RouteHead />
          <DashboardLayout>
            {/* Boundary outside Suspense: a chunk that fails to download is a
                render-time throw, and this way it surfaces as the recoverable
                fallback instead of an unhandled rejection. */}
            <ErrorBoundary>
              <Suspense fallback={<RouteFallback />}>
                <Routes>
                  {ROUTES.map(({ path }) => {
                    // "/" stays eager: it is the first paint, and a loading
                    // fallback there would be a flash of nothing on every cold
                    // visit.
                    const Page = path === "/" ? RepositoryScanner : PAGES[path];
                    return <Route key={path} path={path} element={<Page />} />;
                  })}
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </ErrorBoundary>
          </DashboardLayout>
        </ScanProvider>
      </BrowserRouter>
    </TooltipProvider.Provider>
    </QueryClientProvider>
  </ThemeProvider>
);

export default App;
