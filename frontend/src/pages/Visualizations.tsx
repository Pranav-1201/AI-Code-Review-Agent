import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PieChart, BarChart3 } from "lucide-react";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart as RPieChart,
  Pie,
  Cell,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  Radar
} from "recharts";

export default function Visualizations() {

  const { currentReport } = useScan();

  if (!currentReport) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground">
        <PieChart className="w-12 h-12 mb-4 opacity-30" />
        <p>Run a scan to see visualizations</p>
      </div>
    );
  }

  const { files, summary, dependencies = [] } = currentReport;

  // ------------------------------------------------
  // Complexity + score data
  // ------------------------------------------------

  const complexityData = files.map((f) => ({
    name: f.name?.replace(".py", "") || "file",
    complexity: f.cyclomaticComplexity ?? 0,
    score: f.score ?? 0,
  }));

  // ------------------------------------------------
  // Issue distribution
  // ------------------------------------------------

  const issueTypeData = [
    {
      name: "Security",
      value: files.reduce(
        (s, f) => s + (f.issues?.filter((i) => i.category === "security").length || 0),
        0
      ),
    },
    {
      name: "Performance",
      value: files.reduce(
        (s, f) => s + (f.issues?.filter((i) => i.category === "performance").length || 0),
        0
      ),
    },
    {
      name: "Style",
      value: files.reduce(
        (s, f) => s + (f.issues?.filter((i) => i.category === "style").length || 0),
        0
      ),
    },
    {
      name: "Logic",
      value: files.reduce(
        (s, f) => s + (f.issues?.filter((i) => i.category === "logic").length || 0),
        0
      ),
    },
    {
      name: "Maintainability",
      value: files.reduce(
        (s, f) => s + (f.issues?.filter((i) => i.category === "maintainability").length || 0),
        0
      ),
    },
  ].filter((d) => d.value > 0);

  const COLORS = [
    "hsl(0, 72%, 55%)",
    "hsl(38, 92%, 50%)",
    "hsl(262, 80%, 60%)",
    "hsl(200, 80%, 55%)",
    "hsl(142, 72%, 50%)",
  ];

  // ------------------------------------------------
  // Radar chart data
  // ------------------------------------------------

  const radarData = [
    {
    metric: "Security",
    value:
    summary.security_issues === 0
    ? 100
    : Math.max(0, 100 - summary.security_issues * 20),
    },
    {
    metric: "Quality",
    value: Math.round(summary.avg_score ?? 0),
    },
    {
      metric: "Docs",
      value:
        files.length === 0
          ? 0
          : Math.round(
              files.reduce((s, f) => s + (f.documentationCoverage ?? 0), 0) /
                files.length
            ),
    },
    {
      metric: "Simplicity",
      value:
        files.length === 0
          ? 0
          : Math.round(
              100 -
                files.reduce(
                  (s, f) => s + Math.min((f.cyclomaticComplexity ?? 0) * 3, 50),
                  0
                ) / files.length
            ),
    },
    {
      metric: "Deps",
      value:
        dependencies.length === 0
          ? 100
          : Math.round(
              (dependencies.filter((d) => !d.isOutdated).length /
                dependencies.length) *
                100
            ),
    },
  ];

  // ------------------------------------------------
  // UI
  // ------------------------------------------------

  return (
    <div className="space-y-6">

      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          Visualization Dashboard
        </h1>
        <p className="text-muted-foreground mt-1">
          Charts and graphs for your codebase analysis
        </p>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">

        {/* Complexity */}
        <Card className="bg-card border-border/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-primary" />
              Complexity by File
            </CardTitle>
          </CardHeader>

          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={complexityData}>
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="complexity" fill="hsl(142, 72%, 50%)" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Issues */}
        <Card className="bg-card border-border/50">
          <CardHeader>
            <CardTitle>Issue Distribution</CardTitle>
          </CardHeader>

          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <RPieChart>
                <Pie
                  data={issueTypeData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  dataKey="value"
                >
                  {issueTypeData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </RPieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Quality */}
        <Card className="bg-card border-border/50">
          <CardHeader>
            <CardTitle>Quality Scores</CardTitle>
          </CardHeader>

          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={complexityData}>
                <XAxis dataKey="name" />
                <YAxis domain={[0, 100]} />
                <Tooltip />
                <Bar dataKey="score" fill="hsl(262, 80%, 60%)" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Radar */}
        <Card className="bg-card border-border/50">
          <CardHeader>
            <CardTitle>Health Radar</CardTitle>
          </CardHeader>

          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <RadarChart data={radarData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="metric" />
                <Radar
                  dataKey="value"
                  stroke="hsl(142, 72%, 50%)"
                  fill="hsl(142, 72%, 50%)"
                  fillOpacity={0.2}
                />
              </RadarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

      </div>
    </div>
  );
}