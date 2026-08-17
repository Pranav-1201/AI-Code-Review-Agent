import { lazy, Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import * as TooltipProvider from "@radix-ui/react-tooltip";
import { Loader2 } from "lucide-react";
import { ScanProvider } from "@/context/ScanContext";
import { DashboardLayout } from "@/components/DashboardLayout";
import { ErrorBoundary } from "@/components/ErrorBoundary";

// The landing route stays eager: it is the first paint, and a loading
// fallback there would be a flash of nothing on every cold visit.
import RepositoryScanner from "@/pages/RepositoryScanner";

// Everything else is lazy. These pages pull recharts, react-markdown and the
// dependency-graph renderer, all of which used to sit in the entry chunk.
const ScanResults = lazy(() => import("@/pages/ScanResults"));
const RepositoryOverview = lazy(() => import("@/pages/RepositoryOverview"));
const FileAnalysis = lazy(() => import("@/pages/FileAnalysis"));
const SecurityReport = lazy(() => import("@/pages/SecurityReport"));
const CodeQuality = lazy(() => import("@/pages/CodeQuality"));
const DependencyAnalysis = lazy(() => import("@/pages/DependencyAnalysis"));
const AISuggestions = lazy(() => import("@/pages/AISuggestions"));
const HealthScore = lazy(() => import("@/pages/HealthScore"));
const ScanHistory = lazy(() => import("@/pages/ScanHistory"));
const IssueExplorer = lazy(() => import("@/pages/IssueExplorer"));
const DuplicateDetection = lazy(() => import("@/pages/DuplicateDetection"));
const Visualizations = lazy(() => import("@/pages/Visualizations"));
const ExportReport = lazy(() => import("@/pages/ExportReport"));
const Settings = lazy(() => import("@/pages/Settings"));
const NotFound = lazy(() => import("@/pages/NotFound"));

const queryClient = new QueryClient();

function RouteFallback() {
  return (
    <div className="flex items-center justify-center py-24" role="status" aria-live="polite">
      <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" aria-hidden="true" />
      <span className="sr-only">Loading page</span>
    </div>
  );
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider.Provider>
      <Toaster richColors position="top-right" />
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ScanProvider>
          <DashboardLayout>
            {/* Boundary outside Suspense: a chunk that fails to download is a
                render-time throw, and this way it surfaces as the recoverable
                fallback instead of an unhandled rejection. */}
            <ErrorBoundary>
              <Suspense fallback={<RouteFallback />}>
                <Routes>
                  <Route path="/" element={<RepositoryScanner />} />
                  <Route path="/results" element={<ScanResults />} />
                  <Route path="/overview" element={<RepositoryOverview />} />
                  <Route path="/file-analysis" element={<FileAnalysis />} />
                  <Route path="/security" element={<SecurityReport />} />
                  <Route path="/quality" element={<CodeQuality />} />
                  <Route path="/dependencies" element={<DependencyAnalysis />} />
                  <Route path="/ai-suggestions" element={<AISuggestions />} />
                  <Route path="/health" element={<HealthScore />} />
                  <Route path="/history" element={<ScanHistory />} />
                  <Route path="/issues" element={<IssueExplorer />} />
                  <Route path="/duplicates" element={<DuplicateDetection />} />
                  <Route path="/visualizations" element={<Visualizations />} />
                  <Route path="/export" element={<ExportReport />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </ErrorBoundary>
          </DashboardLayout>
        </ScanProvider>
      </BrowserRouter>
    </TooltipProvider.Provider>
  </QueryClientProvider>
);

export default App;
