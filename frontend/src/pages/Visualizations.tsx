import { useScan } from "@/context/ScanContext";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PieChart, BarChart3, Activity } from "lucide-react";

import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer,
  PieChart as RPieChart, Pie, Cell, Legend,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  ScatterChart, Scatter, ZAxis, CartesianGrid,
} from "recharts";

// Custom tooltip matching the dark theme
const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-card border border-border/50 rounded-lg px-3 py-2 shadow-xl">
      <p className="text-xs font-mono text-muted-foreground mb-1">{label}</p>
      {payload.map((entry: any, i: number) => (
        <p key={i} className="text-sm font-mono" style={{ color: entry.color }}>
          {entry.name}: <span className="font-bold">{entry.value}</span>
        </p>
      ))}
    </div>
  );
};

// Custom tick for angled labels - truncated to maxLen
const AngledTick = ({ x, y, payload }: any) => {
  const label = payload?.value || "";
  const truncated = label.length > 12 ? label.substring(0, 12) + "…" : label;
  return (
    <g transform={`translate(${x},${y})`}>
      <text
        x={0} y={0} dy={8}
        textAnchor="end"
        fill="hsl(215, 15%, 55%)"
        fontSize={10}
        fontFamily="'JetBrains Mono', monospace"
        transform="rotate(-40)"
      >
        {truncated}
      </text>
    </g>
  );
};

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

  const codeFiles = files.filter((f) => f.cyclomaticComplexity > 0 || f.issues.length > 0 || f.score < 100);

  // Complexity: top 15 files sorted by CC
  const complexityData = [...codeFiles]
    .sort((a, b) => b.cyclomaticComplexity - a.cyclomaticComplexity)
    .slice(0, 15)
    .map((f) => ({
      name: f.name.replace(/\.[^/.]+$/, ""),
      complexity: f.cyclomaticComplexity,
      score: f.score,
    }));

  // Quality: top 15 files sorted by worst score
  const qualityData = [...codeFiles]
    .sort((a, b) => a.score - b.score)
    .slice(0, 15)
    .map((f) => ({
      name: f.name.replace(/\.[^/.]+$/, ""),
      score: f.score,
    }));

  // Issue distribution
  const categories = ["security", "performance", "style", "logic", "maintainability"] as const;
  const issueTypeData = categories.map((cat) => ({
    name: cat.charAt(0).toUpperCase() + cat.slice(1),
    value: files.reduce((s, f) => s + f.issues.filter((i) => i.category === cat).length, 0),
  })).filter((d) => d.value > 0);

  const COLORS = [
    "hsl(0, 72%, 55%)",
    "hsl(38, 92%, 50%)",
    "hsl(262, 80%, 60%)",
    "hsl(200, 80%, 55%)",
    "hsl(142, 72%, 50%)",
  ];

  // Radar
  const secScore = summary.security_issues === 0 ? 100 : Math.max(0, Math.round(100 - Math.log2(summary.security_issues + 1) * 15));
  const avgDoc = summary.avg_documentation_coverage ?? Math.round(files.reduce((s, f) => s + (f.documentationCoverage ?? 0), 0) / Math.max(files.length, 1));
  const avgCC = summary.avg_cyclomatic_complexity ?? Math.round(files.reduce((s, f) => s + (f.cyclomaticComplexity ?? 0), 0) / Math.max(files.length, 1));

  const radarData = [
    { metric: "Security", value: secScore },
    { metric: "Quality", value: Math.round(summary.avg_score) },
    { metric: "Docs", value: avgDoc },
    { metric: "Simplicity", value: Math.max(0, Math.round(100 - Math.min(avgCC * 2, 80))) },
    {
      metric: "Dependencies",
      value: dependencies.length === 0
        ? 100
        : Math.round((dependencies.filter((d) => !d.isOutdated).length / dependencies.length) * 100),
    },
  ];

  // Scatter: score vs complexity
  const scatterData = codeFiles.map((f) => ({
    name: f.name,
    score: f.score,
    complexity: f.cyclomaticComplexity,
    lines: f.linesOfCode,
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Visualization Dashboard</h1>
        <p className="text-muted-foreground mt-1">Charts and graphs for your codebase analysis</p>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Complexity */}
        <Card className="bg-card border-border/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-primary" />
              Complexity by File (Top 15)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={340}>
              <BarChart data={complexityData} margin={{ top: 5, right: 20, left: 0, bottom: 60 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(220, 14%, 14%)" />
                <XAxis dataKey="name" tick={<AngledTick />} interval={0} />
                <YAxis tick={{ fill: "hsl(215, 15%, 55%)", fontSize: 11, fontFamily: "'JetBrains Mono'" }} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="complexity" fill="hsl(142, 72%, 50%)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Issue Distribution */}
        <Card className="bg-card border-border/50">
          <CardHeader>
            <CardTitle>Issue Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={340}>
              <RPieChart>
                <Pie
                  data={issueTypeData}
                  cx="50%" cy="45%"
                  innerRadius={60} outerRadius={100}
                  dataKey="value"
                  label={({ name, value }) => `${name}: ${value}`}
                  labelLine={{ stroke: "hsl(215, 15%, 40%)" }}
                >
                  {issueTypeData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
                <Legend
                  verticalAlign="bottom"
                  height={36}
                  wrapperStyle={{ fontSize: 12, fontFamily: "Inter" }}
                />
              </RPieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Quality Scores */}
        <Card className="bg-card border-border/50">
          <CardHeader>
            <CardTitle>Quality Scores (Lowest Files)</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={340}>
              <BarChart data={qualityData} margin={{ top: 5, right: 20, left: 0, bottom: 60 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(220, 14%, 14%)" />
                <XAxis dataKey="name" tick={<AngledTick />} interval={0} />
                <YAxis domain={[0, 100]} tick={{ fill: "hsl(215, 15%, 55%)", fontSize: 11, fontFamily: "'JetBrains Mono'" }} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="score" radius={[4, 4, 0, 0]}>
                  {qualityData.map((entry, i) => (
                    <Cell key={i} fill={entry.score >= 80 ? "hsl(142, 72%, 50%)" : entry.score >= 60 ? "hsl(38, 92%, 50%)" : "hsl(0, 72%, 55%)"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Health Radar */}
        <Card className="bg-card border-border/50">
          <CardHeader>
            <CardTitle>Health Radar</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={340}>
              <RadarChart data={radarData}>
                <PolarGrid stroke="hsl(220, 14%, 18%)" />
                <PolarAngleAxis
                  dataKey="metric"
                  tick={{ fill: "hsl(215, 15%, 70%)", fontSize: 12, fontFamily: "Inter" }}
                />
                <PolarRadiusAxis
                  angle={90}
                  domain={[0, 100]}
                  tick={{ fill: "hsl(215, 15%, 45%)", fontSize: 10 }}
                />
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

        {/* Score vs Complexity scatter */}
        {scatterData.length > 0 && (
          <Card className="lg:col-span-2 bg-card border-border/50">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="w-5 h-5 text-accent" />
                Score vs Complexity
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={340}>
                <ScatterChart margin={{ top: 10, right: 30, left: 0, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(220, 14%, 14%)" />
                  <XAxis
                    type="number" dataKey="complexity" name="Cyclomatic"
                    tick={{ fill: "hsl(215, 15%, 55%)", fontSize: 11, fontFamily: "'JetBrains Mono'" }}
                    label={{ value: "Cyclomatic Complexity", position: "bottom", fill: "hsl(215, 15%, 45%)", fontSize: 11 }}
                  />
                  <YAxis
                    type="number" dataKey="score" name="Score" domain={[0, 100]}
                    tick={{ fill: "hsl(215, 15%, 55%)", fontSize: 11, fontFamily: "'JetBrains Mono'" }}
                    label={{ value: "Quality Score", angle: -90, position: "insideLeft", fill: "hsl(215, 15%, 45%)", fontSize: 11 }}
                  />
                  <ZAxis type="number" dataKey="lines" range={[40, 400]} name="Lines" />
                  <Tooltip content={<CustomTooltip />} />
                  <Scatter data={scatterData} fill="hsl(262, 80%, 60%)" />
                </ScatterChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}