import { useState, useRef } from "react";
import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Search, GitBranch, Loader2, Terminal, AlertCircle } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { useNavigate } from "react-router-dom";

const scanSteps = [
  "Sending request to backend...",
  "Preparing analysis...",
  "Cloning repository...",
  "Scanning files...",
  "Running code analysis...",
  "Checking security vulnerabilities...",
  "Generating AI explanations...",
  "Waiting for results...",
];

export default function RepositoryScanner() {
  const [repoUrl, setRepoUrl] = useState("");
  const { triggerScan, isScanning, scanError } = useScan();
  const [currentStep, setCurrentStep] = useState(0);
  const [elapsedTime, setElapsedTime] = useState(0);
  const navigate = useNavigate();
  const intervalsRef = useRef<{ step?: NodeJS.Timeout; timer?: NodeJS.Timeout }>({});

  const clearIntervals = () => {
    if (intervalsRef.current.step) clearInterval(intervalsRef.current.step);
    if (intervalsRef.current.timer) clearInterval(intervalsRef.current.timer);
    intervalsRef.current = {};
  };

  const handleScan = async () => {
    if (!repoUrl) return;
    setCurrentStep(0);
    setElapsedTime(0);

    intervalsRef.current.step = setInterval(() => {
      setCurrentStep((prev) => Math.min(prev + 1, scanSteps.length - 1));
    }, 5000);

    intervalsRef.current.timer = setInterval(() => {
      setElapsedTime((prev) => prev + 1);
    }, 1000);

    try {
      await triggerScan(repoUrl);
      clearIntervals();
      navigate("/results");
    } catch {
      // Error is already set in ScanContext — just stop the timers
      clearIntervals();
    }
  };

  const formatTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

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
            />
            <Button onClick={handleScan} disabled={isScanning || !repoUrl} className="gap-2 min-w-[140px]">
              {isScanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              {isScanning ? "Scanning..." : "Scan"}
            </Button>
          </div>

          {isScanning && (
            <div className="space-y-3 pt-2">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>Analyzing repository...</span>
                <span>{formatTime(elapsedTime)}</span>
              </div>
              <Progress value={Math.min(((currentStep + 1) / scanSteps.length) * 90, 90)} className="h-1.5" />
              <div className="space-y-1">
                {scanSteps.map((step, i) => (
                  <div key={i} className={`flex items-center gap-2 text-sm font-mono transition-opacity ${i <= currentStep ? "opacity-100" : "opacity-20"}`}>
                    <Terminal className="w-3 h-3 text-primary" />
                    <span className={i === currentStep ? "text-primary" : "text-muted-foreground"}>{step}</span>
                  </div>
                ))}
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
                className="text-left p-3 rounded-md bg-secondary/30 hover:bg-secondary/50 font-mono text-sm text-muted-foreground hover:text-foreground transition-colors"
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
