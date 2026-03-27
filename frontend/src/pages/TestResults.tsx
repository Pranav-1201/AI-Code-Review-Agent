import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TestTube, CheckCircle } from "lucide-react";
import { mockTestResults } from "@/lib/mock-data";

export default function TestResults() {
  const tests = mockTestResults;
  const passed = tests.filter((t) => t.status === "passed").length;
  const totalDuration = tests.reduce((s, t) => s + t.duration, 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Test Results</h1>
        <p className="text-muted-foreground mt-1">Backend test suite status</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card className="bg-card border-primary/30">
          <CardContent className="pt-6 text-center">
            <p className="text-3xl font-bold font-mono text-primary">{passed}/{tests.length}</p>
            <p className="text-xs text-muted-foreground mt-1">Tests Passed</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-border/50">
          <CardContent className="pt-6 text-center">
            <p className="text-3xl font-bold font-mono">{totalDuration.toFixed(1)}s</p>
            <p className="text-xs text-muted-foreground mt-1">Total Duration</p>
          </CardContent>
        </Card>
        <Card className="bg-card border-border/50">
          <CardContent className="pt-6 text-center">
            <p className="text-3xl font-bold font-mono text-primary">100%</p>
            <p className="text-xs text-muted-foreground mt-1">Pass Rate</p>
          </CardContent>
        </Card>
      </div>

      <Card className="bg-card border-border/50">
        <CardHeader><CardTitle className="flex items-center gap-2"><TestTube className="w-5 h-5 text-primary" />Test Suite</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {tests.map((test) => (
            <div key={test.name} className="flex items-center justify-between p-3 rounded-lg bg-secondary/20">
              <div className="flex items-center gap-3">
                <CheckCircle className="w-4 h-4 text-primary" />
                <span className="font-mono text-sm">{test.name}</span>
              </div>
              <div className="flex items-center gap-3">
                <Badge variant="outline" className="text-[10px]">{test.module}</Badge>
                <span className="font-mono text-xs text-muted-foreground">{test.duration.toFixed(2)}s</span>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
