import { useState, useMemo } from "react";
import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SeverityBadge } from "@/components/SeverityBadge";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Search, Filter, AlertTriangle, FileCode, Beaker, FileKey, Layers, Activity } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { getDisplayName } from "@/lib/response-mapper";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";

const VISIBLE_FILES = 50; // Virtual limit for sidebar

// Helper to render code with line numbers and optional patch coloring
const CodeViewer = ({ code, isPatch = false }: { code: string; isPatch?: boolean }) => {
  if (!code) return <span>Not available</span>;

  const lines = code.split("\n");
  
  return (
    <div className="flex flex-col font-mono text-[13px] leading-snug w-full min-w-max">
      {lines.map((line, i) => {
        let bgColor = "transparent";
        let textColor = "text-foreground/80";

        if (isPatch) {
          if (line.startsWith("+") && !line.startsWith("+++")) {
            bgColor = "bg-primary/20";
            textColor = "text-primary border-l-2 border-primary";
          } else if (line.startsWith("-") && !line.startsWith("---")) {
            bgColor = "bg-destructive/20";
            textColor = "text-destructive border-l-2 border-destructive";
          } else if (line.startsWith("@@")) {
            textColor = "text-info font-bold";
            bgColor = "bg-info/10";
          } else {
            textColor = "text-muted-foreground";
          }
        }

        return (
          <div key={i} className={`flex px-2 hover:bg-white/5 ${bgColor}`}>
            <span className="w-10 shrink-0 text-muted-foreground/50 select-none text-right pr-4 border-r border-border/50 mr-4">
              {i + 1}
            </span>
            <span className={`whitespace-pre ${textColor}`}>
              {line || " "}
            </span>
          </div>
        );
      })}
    </div>
  );
};


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
                <div className="flex items-center gap-1.5">
                  <p className="font-mono text-xs truncate flex-1" title={f.path}>
                    {getDisplayName(f, currentReport.files)}
                  </p>
                  {f.fileType === "test" && (
                    <Badge variant="outline" className="text-[8px] px-1 py-0 bg-blue-500/10 text-blue-400 border-blue-500/30 shrink-0">TEST</Badge>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <Progress value={f.score} className="flex-1 h-1 bg-secondary" />
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
          <div className="lg:col-span-3 space-y-4 min-w-0">
            <Card className="bg-card border-border/50">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="font-mono text-sm truncate pr-4" title={file.path}>{file.path}</CardTitle>
                  <span className={`text-2xl font-bold font-mono ${file.score >= 80 ? "text-primary" : file.score >= 60 ? "text-warning" : "text-destructive"}`}>
                    {file.score}/100
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                  <div className="p-3 rounded-lg bg-secondary/20">
                    <p className="text-xs text-muted-foreground">Cyclomatic</p>
                    <p className={`font-mono font-bold mt-1 ${file.cyclomaticComplexity > 10 ? (file.cyclomaticComplexity > 30 ? "text-destructive" : "text-warning") : "text-primary"}`}>
                      {file.cyclomaticComplexity}
                    </p>
                  </div>
                  <div className="p-3 rounded-lg bg-secondary/20">
                    <p className="text-xs text-muted-foreground">Max Nesting</p>
                    <p className={`font-mono font-bold mt-1 ${(file.maxNestingDepth || 0) > 2 ? "text-warning" : "text-primary"}`}>
                      {file.maxNestingDepth !== undefined ? file.maxNestingDepth : "N/A"}
                    </p>
                  </div>
                  <div className="p-3 rounded-lg bg-secondary/20">
                    <p className="text-xs text-muted-foreground">Branches</p>
                    <p className="font-mono font-bold mt-1">{file.branches !== undefined ? file.branches : "N/A"}</p>
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

                {file.breakdown && Object.keys(file.breakdown).length > 0 && (
                  <div className="mt-4 pt-4 border-t border-border/50">
                    <p className="text-xs text-muted-foreground mb-2">Score Breakdown</p>
                    <div className="flex gap-4">
                      {Object.entries(file.breakdown).map(([key, value]) => (
                        <div key={key} className="flex items-center gap-1.5 text-sm">
                          <span className="capitalize">{key}:</span>
                          <span className={value < 0 ? "text-destructive font-bold" : value > 0 ? "text-primary font-bold" : ""}>
                            {value > 0 ? `+${value}` : value}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="bg-card border-border/50">
              <CardHeader><CardTitle className="text-lg flex items-center gap-2"><Beaker className="w-5 h-5 text-primary" /> Hybrid Analysis</CardTitle></CardHeader>
              <CardContent>
                <div className="prose prose-sm prose-invert max-w-none prose-h3:text-primary prose-h3:font-semibold prose-h3:mt-3 prose-p:leading-relaxed">
                  <ReactMarkdown rehypePlugins={[rehypeSanitize]}>
                    {file.explanation || "No explanation generated."}
                  </ReactMarkdown>
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
                        <p className="text-sm font-semibold">{issue.message}</p>
                        {issue.why_it_matters && (
                          <p className="text-xs text-muted-foreground mt-1.5"><span className="font-medium text-foreground/80">Context:</span> {issue.why_it_matters}</p>
                        )}
                        {issue.how_to_fix && (
                          <p className="text-xs text-primary/80 mt-1"><span className="font-medium text-primary">Fix:</span> {issue.how_to_fix}</p>
                        )}
                        <div className="flex gap-2 mt-2">
                          {issue.line && <Badge variant="outline" className="text-[10px] font-mono">Line {issue.line}</Badge>}
                          <Badge variant="outline" className="text-[10px]">{issue.category}</Badge>
                          {issue.confidence && <Badge variant="outline" className="text-[10px] border-primary/20 text-primary/80">{(issue.confidence * 100).toFixed(0)}% Match</Badge>}
                        </div>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            <Card className="bg-card border-border/50 min-w-0">
              <CardHeader><CardTitle className="text-lg">Code</CardTitle></CardHeader>
              <CardContent className="min-w-0">
                <Tabs defaultValue="original">
                  <TabsList className="bg-secondary/30">
                    <TabsTrigger value="original">Original</TabsTrigger>
                    <TabsTrigger value="improved">Improved</TabsTrigger>
                    {file.patch && <TabsTrigger value="patch">Patch</TabsTrigger>}
                  </TabsList>
                  <TabsContent value="original" className="min-w-0">
                    <div className="bg-background border border-border/50 rounded-lg overflow-x-auto overflow-y-auto max-h-[600px] py-4 shadow-inner">
                      <CodeViewer code={file.original_code} />
                    </div>
                  </TabsContent>
                  <TabsContent value="improved" className="min-w-0">
                    <div className="bg-background border border-border/50 rounded-lg overflow-x-auto overflow-y-auto max-h-[600px] py-4 shadow-inner">
                       <CodeViewer code={file.improved_code} />
                    </div>
                  </TabsContent>
                  {file.patch && (
                    <TabsContent value="patch" className="min-w-0">
                      <div className="bg-background border border-border/50 rounded-lg overflow-x-auto overflow-y-auto max-h-[600px] py-4 shadow-inner">
                         <CodeViewer code={file.patch} isPatch />
                      </div>
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
