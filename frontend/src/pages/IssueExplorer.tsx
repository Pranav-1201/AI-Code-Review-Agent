import { useState } from "react";
import { useScan } from "@/context/ScanContext";
import { EmptyState } from "@/components/EmptyState";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { FindingCard } from "@/components/FindingCard";
import { fromFileIssue } from "@/lib/findings";
import { AlertTriangle, Search } from "lucide-react";

export default function IssueExplorer() {
  const { currentReport } = useScan();
  const [searchTerm, setSearchTerm] = useState("");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");

  if (!currentReport) {
    return (
      <EmptyState icon={AlertTriangle} title="Run a scan to explore issues" />
    );
  }

  const allIssues = currentReport.files.flatMap((f) =>
    f.issues.map((issue) => ({
      view: fromFileIssue(issue, f),
      severity: issue.severity,
      category: issue.category,
      message: issue.message,
      fileName: f.name,
    }))
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
            <SelectItem value="Info">Info</SelectItem>
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
          <FindingCard key={i} finding={issue.view} />
        ))}
      </div>
    </div>
  );
}
