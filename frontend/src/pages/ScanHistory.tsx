import { useScan } from "@/context/ScanContext";
import { Card, CardContent } from "@/components/ui/card";
import { History, ExternalLink } from "lucide-react";
import { ScoreRing } from "@/components/ScoreRing";

export default function ScanHistory() {
  const { scanHistory } = useScan();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Scan History</h1>
        <p className="text-muted-foreground mt-1">Previous scans and reports</p>
      </div>

      {scanHistory.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-[40vh] text-muted-foreground">
          <History className="w-12 h-12 mb-4 opacity-30" />
          <p>No scan history yet</p>
        </div>
      ) : (
        <div className="space-y-3">
          {scanHistory.map((scan) => (
            <Card key={scan.id} className="bg-card border-border/50 hover:border-primary/30 transition-colors cursor-pointer">
              <CardContent className="pt-6">
                <div className="flex items-center gap-6">
                  <ScoreRing score={scan.healthScore} size={60} />
                  <div className="flex-1 min-w-0">
                    <h3 className="font-mono font-semibold">{scan.repoName}</h3>
                    <p className="text-xs text-muted-foreground font-mono truncate">{scan.repoUrl}</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {new Date(scan.timestamp).toLocaleDateString()} · {scan.filesAnalyzed} files · {scan.issuesFound} issues
                    </p>
                  </div>
                  <ExternalLink className="w-4 h-4 text-muted-foreground" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
