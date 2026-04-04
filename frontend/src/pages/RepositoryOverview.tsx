import { useState, useMemo } from "react";
import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreRing } from "@/components/ScoreRing";
import { Badge } from "@/components/ui/badge";
import { GitBranch, FileCode, Code2, AlertTriangle, ChevronRight, ChevronDown, Folder, FolderOpen, CheckCircle2, ShieldCheck, Layers } from "lucide-react";

// ----------------------------------------------------------
// Tree Builder
// ----------------------------------------------------------

interface TreeNode {
  name: string;
  path: string;
  isDir: boolean;
  children: TreeNode[];
  // File metadata (only for files)
  score?: number;
  language?: string;
  lines?: number;
}

function buildFileTree(files: { path: string; score: number; language: string; linesOfCode: number }[]): TreeNode {
  const root: TreeNode = { name: "root", path: "", isDir: true, children: [] };

  for (const file of files) {
    const parts = file.path.replace(/\\/g, "/").split("/");
    let current = root;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isLast = i === parts.length - 1;

      let child = current.children.find((c) => c.name === part);

      if (!child) {
        child = {
          name: part,
          path: parts.slice(0, i + 1).join("/"),
          isDir: !isLast,
          children: [],
          ...(isLast ? { score: file.score, language: file.language, lines: file.linesOfCode } : {}),
        };
        current.children.push(child);
      }

      current = child;
    }
  }

  // Sort: directories first, then alphabetically
  function sortTree(node: TreeNode) {
    node.children.sort((a, b) => {
      if (a.isDir && !b.isDir) return -1;
      if (!a.isDir && b.isDir) return 1;
      return a.name.localeCompare(b.name);
    });
    node.children.forEach(sortTree);
  }

  sortTree(root);
  return root;
}

// ----------------------------------------------------------
// Tree Node Component
// ----------------------------------------------------------

function TreeNodeView({ node, depth = 0 }: { node: TreeNode; depth?: number }) {
  const [expanded, setExpanded] = useState(depth < 2);

  if (node.isDir) {
    return (
      <div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1.5 w-full text-left py-1 px-1 rounded hover:bg-secondary/30 transition-colors group"
          style={{ paddingLeft: `${depth * 16 + 4}px` }}
        >
          {expanded ? (
            <ChevronDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
          )}
          {expanded ? (
            <FolderOpen className="w-4 h-4 text-warning shrink-0" />
          ) : (
            <Folder className="w-4 h-4 text-warning shrink-0" />
          )}
          <span className="text-sm font-medium truncate">{node.name}</span>
          <span className="text-xs text-muted-foreground ml-auto shrink-0">
            {node.children.length}
          </span>
        </button>
        {expanded && (
          <div>
            {node.children.map((child) => (
              <TreeNodeView key={child.path} node={child} depth={depth + 1} />
            ))}
          </div>
        )}
      </div>
    );
  }

  // File node
  return (
    <div
      className="flex items-center gap-1.5 py-1 px-1 rounded hover:bg-secondary/20 transition-colors"
      style={{ paddingLeft: `${depth * 16 + 4}px` }}
    >
      <div className="w-3.5 h-3.5 shrink-0" /> {/* spacing for alignment */}
      <FileCode className="w-4 h-4 text-primary shrink-0" />
      <span className="text-sm font-mono truncate flex-1">{node.name}</span>
      {node.lines !== undefined && (
        <span className="text-[10px] text-muted-foreground shrink-0">{node.lines}L</span>
      )}
      {node.score !== undefined && (
        <span
          className={`text-xs font-mono font-bold shrink-0 ${
            node.score >= 80 ? "text-primary" : node.score >= 60 ? "text-warning" : "text-destructive"
          }`}
        >
          {node.score}
        </span>
      )}
    </div>
  );
}

// ----------------------------------------------------------
// Main Component
// ----------------------------------------------------------

export default function RepositoryOverview() {
  const { currentReport } = useScan();

  const fileTree = useMemo(() => {
    if (!currentReport) return null;
    return buildFileTree(currentReport.files);
  }, [currentReport]);

  if (!currentReport) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground">
        <GitBranch className="w-12 h-12 mb-4 opacity-30" />
        <p>Run a scan to see the repository overview</p>
      </div>
    );
  }

  const { summary, files } = currentReport;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Repository Overview</h1>
        <p className="text-muted-foreground font-mono text-sm mt-1">{currentReport.repoName}</p>
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        <Card className="bg-card border-border/50 flex flex-col">
          <CardHeader><CardTitle className="text-sm text-muted-foreground">Project Health</CardTitle></CardHeader>
          <CardContent className="flex flex-col items-center justify-center flex-1">
            <ScoreRing score={summary.healthScore} size={140} />
            <div className="mt-4 text-center">
              <p className="text-xs text-muted-foreground">Computed exclusively from</p>
              <p className="text-sm font-semibold">{summary.production_files || 0} production files</p>
              {summary.test_files > 0 && (
                <p className="text-[10px] text-muted-foreground/60 mt-1">
                  ({summary.test_files} non-production files excluded)
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card border-border/50">
          <CardHeader><CardTitle className="text-sm text-muted-foreground">Languages</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {summary.languages.map((lang) => (
              <div key={lang.name} className="flex items-center gap-3">
                <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: lang.color }} />
                <span className="flex-1 text-sm">{lang.name}</span>
                <Badge variant="outline" className="font-mono">{lang.percentage}%</Badge>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="bg-card border-border/50">
          <CardHeader><CardTitle className="text-sm text-muted-foreground">Quick Stats</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground flex items-center gap-2"><FileCode className="w-4 h-4" /> Files</span>
              <span className="font-mono font-bold">{summary.files}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground flex items-center gap-2"><Code2 className="w-4 h-4" /> Lines of Code</span>
              <span className="font-mono font-bold">{summary.totalLines.toLocaleString()}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground flex items-center gap-2"><AlertTriangle className="w-4 h-4" /> Issues</span>
              <span className="font-mono font-bold">{files.reduce((s, f) => s + f.issues.length, 0)}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {currentReport.insights && (
        <Card className="bg-primary/5 border-primary/20">
          <CardHeader><CardTitle className="text-lg flex items-center gap-2"><ShieldCheck className="w-5 h-5 text-primary" /> Key Insights</CardTitle></CardHeader>
          <CardContent className="grid md:grid-cols-2 gap-6">
            
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-warning" /> Top Actions Needed
              </h3>
              {currentReport.insights.top_critical_issues.length > 0 ? (
                 <ul className="space-y-2">
                    {currentReport.insights.top_critical_issues.slice(0,3).map((issue: any, i: number) => (
                      <li key={i} className="text-sm bg-card p-3 rounded-lg border border-border/50 flex flex-col gap-1">
                        <span className="font-semibold text-foreground/90">{issue.message}</span>
                        <span className="text-xs text-muted-foreground truncate font-mono">Found in {issue.affected_files.length} file(s)</span>
                      </li>
                    ))}
                 </ul>
              ) : (
                <div className="text-sm bg-card p-3 rounded-lg border border-border/50 flex items-center gap-2 text-primary">
                  <CheckCircle2 className="w-4 h-4" /> No critical issues detected.
                </div>
              )}
            </div>

            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
                <Layers className="w-4 h-4 text-info" /> Architecture & Dependencies
              </h3>
              <ul className="space-y-2">
                {currentReport.insights.most_central_file && currentReport.insights.most_central_file !== "None" && (
                   <li className="text-sm bg-card p-3 rounded-lg border border-border/50 flex justify-between items-center">
                     <span className="text-muted-foreground">Most Central Hub</span>
                     <span className="font-mono text-xs truncate max-w-[200px]" title={currentReport.insights.most_central_file}>{currentReport.insights.most_central_file}</span>
                   </li>
                )}
                {currentReport.insights.most_reused_module && currentReport.insights.most_reused_module !== "None" && (
                   <li className="text-sm bg-card p-3 rounded-lg border border-border/50 flex justify-between items-center">
                     <span className="text-muted-foreground">Highest Reuse</span>
                     <span className="font-mono text-xs truncate max-w-[200px]" title={currentReport.insights.most_reused_module}>{currentReport.insights.most_reused_module}</span>
                   </li>
                )}
                {currentReport.insights.most_complex_files.length > 0 && (
                  <li className="text-sm bg-card p-3 rounded-lg border border-border/50 flex justify-between items-center">
                     <span className="text-muted-foreground">Highest Complexity</span>
                     <span className="font-mono text-xs truncate max-w-[200px]" title={currentReport.insights.most_complex_files[0].file_path}>{currentReport.insights.most_complex_files[0].file_path}</span>
                   </li>
                )}
              </ul>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Architecture Tree */}
      <Card className="bg-card border-border/50">
        <CardHeader><CardTitle>Architecture Overview</CardTitle></CardHeader>
        <CardContent>
          {fileTree && fileTree.children.length > 0 ? (
            <div className="max-h-[500px] overflow-y-auto rounded-lg border border-border/30 bg-background/50 p-2">
              {fileTree.children.map((child) => (
                <TreeNodeView key={child.path} node={child} depth={0} />
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground text-sm">No files analyzed yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
