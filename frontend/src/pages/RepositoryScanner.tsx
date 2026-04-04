import { useState, useRef, useEffect } from "react";
import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Search, GitBranch, Loader2, Terminal, AlertCircle, CheckCircle2 } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { useNavigate } from "react-router-dom";

export default function RepositoryScanner() {
  const [repoUrl, setRepoUrl] = useState("");
  const { triggerScan, isScanning, scanError, scanStatus } = useScan();
  const [elapsedTime, setElapsedTime] = useState(0);
  const navigate = useNavigate();
  const timerRef = useRef<NodeJS.Timeout>();

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
  };

  useEffect(() => {
    if (isScanning) {
      setElapsedTime(0);
      timerRef.current = setInterval(() => {
        setElapsedTime((prev) => prev + 1);
      }, 1000);
    } else {
      clearTimer();
    }
    return clearTimer;
  }, [isScanning]);

  const handleScan = async () => {
    if (!repoUrl) return;

    try {
      await triggerScan(repoUrl);
      navigate("/results");
    } catch {
      // Error handled by context
    }
  };

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

  // Stages definition
  const stages = [
    { id: "initializing", label: "Starting up" },
    { id: "cloning", label: "Cloning repository" },
    { id: "discovery", label: "Discovering files" },
    { id: "dependencies", label: "Mapping dependencies" },
    { id: "analysis", label: "Running AI analysis" },
    { id: "finalizing", label: "Computing scores" },
    { id: "complete", label: "Complete" },
  ];

  const currentStageIndex = scanStatus?.stage
    ? stages.findIndex(s => s.id === scanStatus.stage)
    : 0;

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Repository Scanner</h1>
        <p className="text-muted-foreground mt-1">Analyze any GitHub repository with AI-powered code review</p>
      </div>

      <Card className="bg-card border-border/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <GitBranch className="w-5 h-5 text-primary" />
            Enter Repository URL
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-3">
            <Input
              placeholder="https://github.com/username/repository"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              className="bg-background border-border font-mono text-sm"
              onKeyDown={(e) => e.key === "Enter" && handleScan()}
              disabled={isScanning}
            />
            <Button onClick={handleScan} disabled={isScanning || !repoUrl} className="gap-2 min-w-[140px]">
              {isScanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              {isScanning ? "Scanning..." : "Scan"}
            </Button>
          </div>

          {isScanning && (
            <div className="space-y-4 pt-2">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span className="font-mono">
                  {scanStatus?.stage_detail || "Connecting to backend..."}
                </span>
                <span>{formatTime(elapsedTime)}</span>
              </div>
              
              <Progress value={scanStatus?.progress || 0} className="h-2 bg-secondary" />
              
              {scanStatus?.files_processed !== undefined && scanStatus?.total_files !== undefined && scanStatus.total_files > 0 && (
                <div className="flex justify-between text-[10px] text-muted-foreground font-mono">
                  <span>Files Processed</span>
                  <span>{scanStatus.files_processed} / {scanStatus.total_files} ({(scanStatus.files_processed / scanStatus.total_files * 100).toFixed(1)}%)</span>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-4 p-4 rounded-lg bg-secondary/20 border border-border/50">
                {stages.map((stage, i) => {
                  const isPast = i < currentStageIndex;
                  const isCurrent = i === currentStageIndex;
                  const isFuture = i > currentStageIndex;

                  return (
                    <div 
                      key={stage.id} 
                      className={`flex items-center gap-2 text-sm font-mono transition-opacity ${
                        isCurrent ? "text-primary opacity-100" : 
                        isPast ? "text-muted-foreground opacity-60" : 
                        "text-muted-foreground opacity-30"
                      }`}
                    >
                      {isPast ? <CheckCircle2 className="w-4 h-4 text-primary/80" /> : <Terminal className="w-4 h-4" />}
                      <span>{stage.label}</span>
                      {isCurrent && <span className="ml-auto w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {scanError && !isScanning && (
            <div className="flex items-start gap-2 text-sm text-destructive bg-destructive/10 p-3 rounded-md">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <div>
                <p className="font-medium">Scan failed</p>
                <p className="mt-1 opacity-80">{scanError}</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="bg-card/50 border-border/30">
        <CardContent className="pt-6">
          <h3 className="text-sm font-semibold mb-3 text-muted-foreground">Quick Start</h3>
          <div className="grid gap-2">
            {["https://github.com/pallets/flask", "https://github.com/fastapi/fastapi", "https://github.com/django/django"].map((url) => (
              <button
                key={url}
                onClick={() => setRepoUrl(url)}
                disabled={isScanning}
                className="text-left p-3 rounded-md bg-secondary/30 hover:bg-secondary/50 font-mono text-sm text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
              >
                {url}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
