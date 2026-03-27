import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Copy, FileCode } from "lucide-react";

export default function DuplicateDetection() {
  const { currentReport } = useScan();

  if (!currentReport) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground">
        <Copy className="w-12 h-12 mb-4 opacity-30" />
        <p>Run a scan to detect duplicates</p>
      </div>
    );
  }

  // Use top-level duplicates from backend if available
  const topLevelDuplicates = currentReport.duplicates || [];

  // Also gather file-level duplicates
  const filesWithDuplicates = currentReport.files.filter((f) => f.duplicates && f.duplicates.length > 0);

  const totalDuplicates = topLevelDuplicates.length || filesWithDuplicates.length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Code Similarity Detection</h1>
        <p className="text-muted-foreground mt-1">{totalDuplicates} duplicate pair{totalDuplicates !== 1 ? "s" : ""} detected</p>
      </div>

      {totalDuplicates === 0 ? (
        <Card className="bg-card border-primary/30">
          <CardContent className="pt-6 text-center">
            <Copy className="w-12 h-12 text-primary mx-auto mb-2" />
            <p className="text-primary font-medium">No significant code duplication detected</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {/* Top-level duplicates (from backend) */}
          {topLevelDuplicates.length > 0 && topLevelDuplicates.map((dup, i) => (
            <Card key={i} className="bg-card border-border/50">
              <CardContent className="pt-6">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <Copy className="w-5 h-5 text-warning shrink-0" />
                    <div className="min-w-0">
                      <p className="font-mono text-sm truncate">{dup.file1}</p>
                      <p className="text-xs text-muted-foreground mt-0.5">↔</p>
                      <p className="font-mono text-sm truncate">{dup.file2}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {dup.type && (
                      <Badge variant="outline" className="text-[10px]">
                        {dup.type === "exact" ? "Exact Match" : "Block Similarity"}
                      </Badge>
                    )}
                    <Badge
                      variant="outline"
                      className={`font-mono ${
                        dup.similarity > 80
                          ? "text-destructive border-destructive/30"
                          : dup.similarity > 50
                          ? "text-warning border-warning/30"
                          : "text-info border-info/30"
                      }`}
                    >
                      {dup.similarity}% similar
                    </Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          {/* File-level duplicates (fallback if no top-level) */}
          {topLevelDuplicates.length === 0 && filesWithDuplicates.map((file) => (
            <Card key={file.path} className="bg-card border-border/50">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base font-mono">
                  <FileCode className="w-5 h-5 text-primary" />
                  {file.path}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {file.duplicates!.map((dup) => (
                  <div key={dup.file} className="flex items-center justify-between p-3 rounded-lg bg-secondary/20">
                    <div className="flex items-center gap-3">
                      <Copy className="w-4 h-4 text-warning" />
                      <span className="font-mono text-sm">{dup.file}</span>
                    </div>
                    <Badge variant="outline" className={`font-mono ${dup.similarity > 80 ? "text-destructive border-destructive/30" : "text-warning border-warning/30"}`}>
                      {dup.similarity}% similar
                    </Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
