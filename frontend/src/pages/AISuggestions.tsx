import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Brain, Lightbulb, FileCode } from "lucide-react";

export default function AISuggestions() {
  const { currentReport } = useScan();

  if (!currentReport) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground">
        <Brain className="w-12 h-12 mb-4 opacity-30" />
        <p>Run a scan to see AI suggestions</p>
      </div>
    );
  }

  const filesWithSuggestions = currentReport.files.filter((f) => f.suggestions.length > 0 || f.explanation);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">AI Suggestions</h1>
        <p className="text-muted-foreground mt-1">AI-generated explanations and recommendations</p>
      </div>

      <div className="space-y-4">
        {filesWithSuggestions.map((file) => (
          <Card key={file.path} className="bg-card border-border/50">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 font-mono text-base">
                <FileCode className="w-5 h-5 text-primary" />
                {file.path}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {file.explanation && (
                <div className="p-4 rounded-lg bg-accent/5 border border-accent/20">
                  <div className="flex items-center gap-2 mb-2">
                    <Brain className="w-4 h-4 text-accent" />
                    <span className="text-sm font-semibold text-accent">AI Analysis</span>
                  </div>
                  <p className="text-sm text-foreground/80 leading-relaxed">{file.explanation}</p>
                </div>
              )}

              {file.suggestions.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-semibold flex items-center gap-2">
                    <Lightbulb className="w-4 h-4 text-warning" />
                    Suggestions
                  </p>
                  {file.suggestions.map((s, i) => (
                    <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-secondary/20">
                      <span className="text-primary font-mono text-sm font-bold">{i + 1}.</span>
                      <p className="text-sm">{s}</p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
