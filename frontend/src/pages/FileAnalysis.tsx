import { useState, useMemo } from "react";
import { useScan } from "@/context/ScanContext";
import { EmptyState } from "@/components/EmptyState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ExplanationSourceBadge } from "@/components/ExplanationSourceBadge";
import { FindingCard } from "@/components/FindingCard";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Search, Filter, AlertTriangle, FileCode, Beaker, FileKey, Layers, Activity } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { getDisplayName } from "@/lib/response-mapper";
import { fromFileIssue } from "@/lib/findings";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import { CodeViewer } from "@/components/CodeViewer";
import { SuggestedEditsPane } from "@/components/SuggestedEditsPane";
import { WhatChangedPane } from "@/components/WhatChangedPane";

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
      <EmptyState icon={FileCode} title="Run a scan to see file analysis" />
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
              <CardHeader><CardTitle className="text-lg flex items-center gap-2"><Beaker className="w-5 h-5 text-primary" /> Hybrid Analysis<ExplanationSourceBadge source={file.explanationSource} className="ml-1" /></CardTitle></CardHeader>
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
                    <FindingCard key={i} finding={fromFileIssue(issue, file)} />
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
                    <TabsTrigger value="suggested">Suggested edits</TabsTrigger>
                    {((file.refactorChanges?.length ?? 0) > 0 || file.patch) && (
                      <TabsTrigger value="changed">What changed</TabsTrigger>
                    )}
                  </TabsList>
                  <TabsContent value="original" className="min-w-0">
                    <div className="bg-background border border-border/50 rounded-lg overflow-x-auto overflow-y-auto max-h-[600px] py-4 shadow-inner">
                      <CodeViewer code={file.original_code} />
                    </div>
                  </TabsContent>
                  <TabsContent value="suggested" className="min-w-0">
                    <SuggestedEditsPane
                      improvedCode={file.improved_code}
                      originalCode={file.original_code}
                      changes={file.refactorChanges ?? []}
                    />
                  </TabsContent>
                  {((file.refactorChanges?.length ?? 0) > 0 || file.patch) && (
                    <TabsContent value="changed" className="min-w-0">
                      <WhatChangedPane changes={file.refactorChanges ?? []} patch={file.patch} />
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
