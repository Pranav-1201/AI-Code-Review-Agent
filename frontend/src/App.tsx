import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import * as TooltipProvider from "@radix-ui/react-tooltip";
import { ScanProvider } from "@/context/ScanContext";
import { DashboardLayout } from "@/components/DashboardLayout";
import RepositoryScanner from "@/pages/RepositoryScanner";
import ScanResults from "@/pages/ScanResults";
import RepositoryOverview from "@/pages/RepositoryOverview";
import FileAnalysis from "@/pages/FileAnalysis";
import SecurityReport from "@/pages/SecurityReport";
import CodeQuality from "@/pages/CodeQuality";
import DependencyAnalysis from "@/pages/DependencyAnalysis";
import AISuggestions from "@/pages/AISuggestions";
import HealthScore from "@/pages/HealthScore";
import ScanHistory from "@/pages/ScanHistory";
import IssueExplorer from "@/pages/IssueExplorer";
import DuplicateDetection from "@/pages/DuplicateDetection";
import Visualizations from "@/pages/Visualizations";
import ExportReport from "@/pages/ExportReport";
import Settings from "@/pages/Settings";
import NotFound from "@/pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider.Provider>
      <Toaster richColors position="top-right" />
      <BrowserRouter>
        <ScanProvider>
          <DashboardLayout>
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
          </DashboardLayout>
        </ScanProvider>
      </BrowserRouter>
    </TooltipProvider.Provider>
  </QueryClientProvider>
);

export default App;
