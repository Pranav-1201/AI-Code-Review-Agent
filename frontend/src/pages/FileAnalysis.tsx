import { useState, useMemo } from "react";
import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SeverityBadge } from "@/components/SeverityBadge";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { FileCode, AlertTriangle, Search, Filter } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const VISIBLE_FILES = 50; // Virtual limit for sidebar

export default function FileAnalysis() {
  const { currentReport } = useScan();
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [languageFilter, setLanguageFilter] = useState("all");
  const [visibleCount, setVisibleCount] = useState(VISIBLE_FILES);

  // Get unique languages from files
  const languages = useMemo(() => {
    if (!currentReport) return [];
    const langs = new Set(currentReport.files.map((f) => f.language));
    return Array.from(langs).filter(Boolean).sort();
  }, [currentReport]);

  // Filter files
  const filteredFiles = useMemo(() => {
    if (!currentReport) return [];

    return currentReport.files.filter((f) => {
      const matchSearch =
        !searchTerm ||
        f.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        f.path.toLowerCase().includes(searchTerm.toLowerCase());

      const matchLanguage =
        languageFilter === "all" || f.language === languageFilter;

      return matchSearch && matchLanguage;
    });
  }, [currentReport, searchTerm, languageFilter]);

  if (!currentReport) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground">
        <FileCode className="w-12 h-12 mb-4 opacity-30" />
        <p>Run a scan to see file analysis</p>
      </div>
    );
  }

  const visibleFiles = filteredFiles.slice(0, visibleCount);

  const file = selectedFilePath
    ? currentReport.files.find((f) => f.path === selectedFilePath)
    : filteredFiles[0];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">File Level Analysis</h1>
        <p className="text-muted-foreground mt-1">Per-file metrics and detailed analysis</p>
      </div>

      <div className="grid lg:grid-cols-4 gap-6">
        {/* Sidebar with filtering */}
        <div className="space-y-3">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search files..."
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setVisibleCount(VISIBLE_FILES);
              }}
              className="pl-9 bg-card border-border h-9 text-sm"
            />
          </div>

          {/* Language filter */}
          <Select value={languageFilter} onValueChange={(v) => {
            setLanguageFilter(v);
            setVisibleCount(VISIBLE_FILES);
          }}>
            <SelectTrigger className="bg-card h-9 text-sm">
              <Filter className="w-3 h-3 mr-2" />
              <SelectValue placeholder="Language" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Languages ({currentReport.files.length})</SelectItem>
              {languages.map((lang) => (
                <SelectItem key={lang} value={lang}>
                  {lang} ({currentReport.files.filter((f) => f.language === lang).length})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* File count */}
          <p className="text-xs text-muted-foreground">
            {filteredFiles.length} file{filteredFiles.length !== 1 ? "s" : ""}
            {searchTerm || languageFilter !== "all" ? " (filtered)" : ""}
          </p>

          {/* File list (virtualized) */}
          <div className="space-y-1.5 max-h-[65vh] overflow-y-auto pr-1">
            {visibleFiles.map((f) => (
              <button
                key={f.path}
                onClick={() => setSelectedFilePath(f.path)}
                className={`w-full text-left p-2.5 rounded-lg border transition-colors ${
                  (selectedFilePath || filteredFiles[0]?.path) === f.path
                    ? "bg-primary/10 border-primary/30 text-primary"
                    : "bg-card border-border/50 hover:border-border"
                }`}
              >
                <p className="font-mono text-xs truncate" title={f.path}>{f.path}</p>
                <div className="flex items-center gap-2 mt-1">
                  <Progress value={f.score} className="flex-1 h-1" />
                  <span className="font-mono text-xs">{f.score}</span>
                </div>
              </button>
            ))}
          </div>

          {/* Load more button */}
          {visibleCount < filteredFiles.length && (
            <button
              onClick={() => setVisibleCount((c) => c + VISIBLE_FILES)}
              className="w-full text-center p-2 rounded-lg border border-border/50 text-sm text-muted-foreground hover:text-foreground hover:border-border transition-colors"
            >
              Show more ({filteredFiles.length - visibleCount} remaining)
            </button>
          )}
        </div>

        {file && (
          <div className="lg:col-span-3 space-y-4">
            <Card className="bg-card border-border/50">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="font-mono text-sm">{file.path}</CardTitle>
                  <span className={`text-2xl font-bold font-mono ${file.score >= 80 ? "text-primary" : file.score >= 60 ? "text-warning" : "text-destructive"}`}>
                    {file.score}/100
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="p-3 rounded-lg bg-secondary/20">
                    <p className="text-xs text-muted-foreground">Complexity</p>
                    <p className="font-mono font-bold mt-1">{file.complexity}</p>
                  </div>
                  <div className="p-3 rounded-lg bg-secondary/20">
                    <p className="text-xs text-muted-foreground">Cyclomatic</p>
                    <p className="font-mono font-bold mt-1">{file.cyclomaticComplexity}</p>
                  </div>
                  <div className="p-3 rounded-lg bg-secondary/20">
                    <p className="text-xs text-muted-foreground">Lines</p>
                    <p className="font-mono font-bold mt-1">{file.linesOfCode}</p>
                  </div>
                  <div className="p-3 rounded-lg bg-secondary/20">
                    <p className="text-xs text-muted-foreground">Doc Coverage</p>
                    <p className="font-mono font-bold mt-1">{file.documentationCoverage}%</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {file.issues.length > 0 && (
              <Card className="bg-card border-border/50">
                <CardHeader><CardTitle className="text-lg flex items-center gap-2"><AlertTriangle className="w-5 h-5 text-warning" /> Issues ({file.issues.length})</CardTitle></CardHeader>
                <CardContent className="space-y-2">
                  {file.issues.map((issue, i) => (
                    <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-secondary/20">
                      <SeverityBadge severity={issue.severity} />
                      <div className="flex-1">
                        <p className="text-sm">{issue.message}</p>
                        <div className="flex gap-2 mt-1">
                          {issue.line && <Badge variant="outline" className="text-[10px] font-mono">Line {issue.line}</Badge>}
                          <Badge variant="outline" className="text-[10px]">{issue.category}</Badge>
                        </div>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            <Card className="bg-card border-border/50">
              <CardHeader><CardTitle className="text-lg">Code</CardTitle></CardHeader>
              <CardContent>
                <Tabs defaultValue="original">
                  <TabsList className="bg-secondary/30">
                    <TabsTrigger value="original">Original</TabsTrigger>
                    <TabsTrigger value="improved">Improved</TabsTrigger>
                    {file.patch && <TabsTrigger value="patch">Patch</TabsTrigger>}
                  </TabsList>
                  <TabsContent value="original">
                    <pre className="p-4 rounded-lg bg-background border border-border/50 overflow-auto font-mono text-sm text-muted-foreground max-h-[500px]">
                      <code>{file.original_code || "Not available"}</code>
                    </pre>
                  </TabsContent>
                  <TabsContent value="improved">
                    <pre className="p-4 rounded-lg bg-background border border-border/50 overflow-auto font-mono text-sm text-primary/90 max-h-[500px]">
                      <code>{file.improved_code || "No improvements suggested"}</code>
                    </pre>
                  </TabsContent>
                  {file.patch && (
                    <TabsContent value="patch">
                      <pre className="p-4 rounded-lg bg-background border border-border/50 overflow-auto font-mono text-sm text-info max-h-[500px]">
                        <code>{file.patch}</code>
                      </pre>
                    </TabsContent>
                  )}
                </Tabs>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
