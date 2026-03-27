import { useState } from "react";
import { useScan } from "@/context/ScanContext";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SeverityBadge } from "@/components/SeverityBadge";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, Search } from "lucide-react";

export default function IssueExplorer() {
  const { currentReport } = useScan();
  const [searchTerm, setSearchTerm] = useState("");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");

  if (!currentReport) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground">
        <AlertTriangle className="w-12 h-12 mb-4 opacity-30" />
        <p>Run a scan to explore issues</p>
      </div>
    );
  }

  const allIssues = currentReport.files.flatMap((f) =>
    f.issues.map((issue) => ({ ...issue, fileName: f.name, filePath: f.path }))
  );

  const filteredIssues = allIssues.filter((issue) => {
    const matchSearch = !searchTerm || issue.message.toLowerCase().includes(searchTerm.toLowerCase()) || issue.fileName.toLowerCase().includes(searchTerm.toLowerCase());
    const matchSeverity = severityFilter === "all" || issue.severity === severityFilter;
    const matchCategory = categoryFilter === "all" || issue.category === categoryFilter;
    return matchSearch && matchSeverity && matchCategory;
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Issue Explorer</h1>
        <p className="text-muted-foreground mt-1">{allIssues.length} issues across {currentReport.files.length} files</p>
      </div>

      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search issues..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-9 bg-card border-border"
          />
        </div>
        <Select value={severityFilter} onValueChange={setSeverityFilter}>
          <SelectTrigger className="w-[140px] bg-card">
            <SelectValue placeholder="Severity" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Severities</SelectItem>
            <SelectItem value="Critical">Critical</SelectItem>
            <SelectItem value="High">High</SelectItem>
            <SelectItem value="Medium">Medium</SelectItem>
            <SelectItem value="Low">Low</SelectItem>
          </SelectContent>
        </Select>
        <Select value={categoryFilter} onValueChange={setCategoryFilter}>
          <SelectTrigger className="w-[160px] bg-card">
            <SelectValue placeholder="Category" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Categories</SelectItem>
            <SelectItem value="security">Security</SelectItem>
            <SelectItem value="performance">Performance</SelectItem>
            <SelectItem value="style">Style</SelectItem>
            <SelectItem value="logic">Logic</SelectItem>
            <SelectItem value="maintainability">Maintainability</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <p className="text-sm text-muted-foreground">{filteredIssues.length} results</p>

      <div className="space-y-2">
        {filteredIssues.map((issue, i) => (
          <Card key={i} className="bg-card border-border/50">
            <CardContent className="py-4">
              <div className="flex items-start gap-3">
                <SeverityBadge severity={issue.severity} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm">{issue.message}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <Badge variant="outline" className="text-[10px] font-mono">{issue.fileName}</Badge>
                    <Badge variant="outline" className="text-[10px]">{issue.category}</Badge>
                    {issue.line && <Badge variant="outline" className="text-[10px] font-mono">L{issue.line}</Badge>}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
