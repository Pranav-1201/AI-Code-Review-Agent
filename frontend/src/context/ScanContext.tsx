import React, { createContext, useContext, useState } from "react";
import { ScanReport, ScanHistoryItem } from "@/lib/types";
import { startAndPollScan } from "@/lib/api";
import { mapApiResponse } from "@/lib/response-mapper";
import { toast } from "sonner";

interface ScanContextType {
  currentReport: ScanReport | null;
  setCurrentReport: (report: ScanReport | null) => void;
  scanHistory: ScanHistoryItem[];
  isScanning: boolean;
  setIsScanning: (v: boolean) => void;
  triggerScan: (repoUrl: string) => Promise<void>;
  scanError: string | null;
}

const ScanContext = createContext<ScanContextType | undefined>(undefined);

export function ScanProvider({ children }: { children: React.ReactNode }) {

  const [currentReport, setCurrentReport] = useState<ScanReport | null>(null);
  const [scanHistory, setScanHistory] = useState<ScanHistoryItem[]>([]);
  const [isScanning, setIsScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);

  const triggerScan = async (repoUrl: string) => {

    setIsScanning(true);
    setScanError(null);

    try {

      const rawData = await startAndPollScan(repoUrl);

      console.log("Raw API Response:", rawData);

      const report = mapApiResponse(rawData, repoUrl);

      // Safety check
      if (!report || !report.files || report.files.length === 0) {
        throw new Error("Scan finished but no files were analyzed.");
      }

      // Store report
      setCurrentReport(report);

      // Update history
      setScanHistory((prev) => [
        {
          id: report.id,
          repoName: report.repoName,
          repoUrl,
          timestamp: report.timestamp,
          healthScore: report.summary.healthScore,
          filesAnalyzed: report.summary.files,
          issuesFound: report.files.reduce(
            (sum, f) => sum + (f.issues ? f.issues.length : 0),
            0
          ),
        },
        ...prev,
      ]);

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

  return (
    <ScanContext.Provider
      value={{
        currentReport,
        setCurrentReport,
        scanHistory,
        isScanning,
        setIsScanning,
        triggerScan,
        scanError,
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