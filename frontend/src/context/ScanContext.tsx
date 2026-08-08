import React, { createContext, useContext, useState, useEffect } from "react";
import { ScanReport, ScanHistoryItem } from "@/lib/types";
import { startAndStreamScan, listScans } from "@/lib/api";
import { mapApiResponse } from "@/lib/response-mapper";
import { mockScanReport, mockScanHistory } from "@/lib/mock-data";
import { toast } from "sonner";

interface ScanStatus {
  status: string;
  progress: number;
  stage?: string;
  stage_detail?: string;
  files_processed?: number;
  total_files?: number;
}

interface ScanContextType {
  currentReport: ScanReport | null;
  setCurrentReport: (report: ScanReport | null) => void;
  scanHistory: ScanHistoryItem[];
  isScanning: boolean;
  setIsScanning: (v: boolean) => void;
  triggerScan: (repoUrl: string) => Promise<void>;
  loadDemo: () => void;
  refreshHistory: () => Promise<void>;
  scanError: string | null;
  scanStatus: ScanStatus | null;
}

const ScanContext = createContext<ScanContextType | undefined>(undefined);

export function ScanProvider({ children }: { children: React.ReactNode }) {

  const [currentReport, setCurrentReport] = useState<ScanReport | null>(null);
  const [scanHistory, setScanHistory] = useState<ScanHistoryItem[]>([]);
  const [isScanning, setIsScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [scanStatus, setScanStatus] = useState<ScanStatus | null>(null);

  // Pull persisted scan history from the backend (Fix K) so it survives a page
  // reload instead of living only in this in-memory context. Backend rows are
  // mapped to ScanHistoryItem. If the backend is unreachable (offline / demo),
  // the existing in-memory history is left untouched.
  const refreshHistory = async () => {
    try {
      const rows = await listScans();
      setScanHistory(
        rows.map((r: any): ScanHistoryItem => ({
          id: r.id,
          repoName: (r.repo || "").split("/").filter(Boolean).pop() || "repository",
          repoUrl: r.repo || "",
          timestamp: r.timestamp || new Date().toISOString(),
          healthScore: r.health_score ?? 0,
          filesAnalyzed: r.files_analyzed ?? 0,
          issuesFound: r.issues_found ?? 0,
        }))
      );
    } catch {
      // Backend unreachable — keep whatever history we already have.
    }
  };

  // Load persisted history once on mount so /history is populated on first load.
  useEffect(() => {
    refreshHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const triggerScan = async (repoUrl: string) => {

    setIsScanning(true);
    setScanError(null);
    setScanStatus(null);

    try {

      const rawData = await startAndStreamScan(repoUrl, (status) => {
        setScanStatus(status);
      });

      console.log("Raw API Response:", rawData);

      if (rawData && rawData.error) {
        throw new Error(`Backend error: ${rawData.error}`);
      }

      const normalized = Array.isArray(rawData)
        ? { file_reports: rawData }
        : rawData;

      const files = normalized?.file_reports
                 ?? normalized?.reports
                 ?? normalized?.files
                 ?? [];

      if (files.length === 0) {
        throw new Error("Scan finished but no files were analyzed.");
      }

      const report = mapApiResponse(normalized, repoUrl);

      // Store report
      setCurrentReport(report);

      // Refresh history from the backend so the just-completed scan appears and
      // the list stays authoritative + persistent across reloads (Fix K).
      await refreshHistory();

      toast.success("Repository scan completed successfully");

    } catch (err: any) {

      console.error("Scan failed:", err);

      const message =
        err?.message || "Repository scan failed. Please try again.";

      setScanError(message);

      toast.error(message);

      throw err;

    } finally {

      setIsScanning(false);

    }
  };

  // Offline demo mode: populate the UI from a static sample report so every
  // page is explorable with no backend running. Deliberately bypasses the
  // scan pipeline — no network, no polling.
  const loadDemo = () => {
    setScanError(null);
    setScanStatus(null);
    setIsScanning(false);
    setCurrentReport(mockScanReport);
    setScanHistory(mockScanHistory);
    toast.success("Loaded demo report (offline sample — no backend needed)");
  };

  return (
    <ScanContext.Provider
      value={{
        currentReport,
        setCurrentReport,
        scanHistory,
        isScanning,
        setIsScanning,
        triggerScan,
        loadDemo,
        refreshHistory,
        scanError,
        scanStatus,
      }}
    >
      {children}
    </ScanContext.Provider>
  );
}

export function useScan() {

  const ctx = useContext(ScanContext);

  if (!ctx) {
    throw new Error("useScan must be used within ScanProvider");
  }

  return ctx;
}