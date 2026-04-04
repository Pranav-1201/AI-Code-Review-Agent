import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Settings as SettingsIcon, Save, RefreshCw, Server, Shield, Brain, Zap, Monitor, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";

export default function SettingsPage() {
  const [settings, setSettings] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const res = await fetch("http://localhost:8000/settings");
      if (!res.ok) throw new Error("Failed to fetch settings");
      const data = await res.json();
      setSettings(data);
    } catch (err) {
      toast.error("Could not load settings from backend");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      const res = await fetch("http://localhost:8000/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      if (!res.ok) throw new Error("Failed to save settings");
      toast.success("Settings saved successfully");
    } catch (err) {
      toast.error("Failed to save settings");
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm("Are you sure you want to reset all settings to defaults?")) return;
    try {
      setLoading(true);
      const res = await fetch("http://localhost:8000/settings/reset", {
        method: "POST",
      });
      if (!res.ok) throw new Error("Failed to reset settings");
      const data = await res.json();
      setSettings(data.settings);
      toast.success("Settings restored to defaults");
    } catch (err) {
      toast.error("Failed to reset settings");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const updateSection = (section: string, key: string, value: any) => {
    setSettings((prev: any) => ({
      ...prev,
      [section]: {
        ...prev[section],
        [key]: value
      }
    }));
  };

  if (loading && !settings) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground">
        <RefreshCw className="w-8 h-8 mb-4 animate-spin opacity-50" />
        <p>Loading settings...</p>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground">
        <p>Could not connect to backend.</p>
        <Button variant="outline" className="mt-4" onClick={fetchSettings}>Retry</Button>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl pb-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
          <p className="text-muted-foreground mt-1">Configure your AI Code Review Agent</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handleReset} disabled={saving || loading}>
            Reset Defaults
          </Button>
          <Button onClick={handleSave} disabled={saving || loading} className="gap-2">
            {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Changes
          </Button>
        </div>
      </div>

      <Tabs defaultValue="analysis" className="w-full">
        <TabsList className="grid w-full grid-cols-6 mb-8">
          <TabsTrigger value="analysis" className="gap-2"><Server className="w-4 h-4" /> Analysis</TabsTrigger>
          <TabsTrigger value="security" className="gap-2"><Shield className="w-4 h-4" /> Security</TabsTrigger>
          <TabsTrigger value="ai" className="gap-2"><Brain className="w-4 h-4" /> AI</TabsTrigger>
          <TabsTrigger value="performance" className="gap-2"><Zap className="w-4 h-4" /> Perf</TabsTrigger>
          <TabsTrigger value="ui" className="gap-2"><Monitor className="w-4 h-4" /> UI</TabsTrigger>
          <TabsTrigger value="export" className="gap-2"><Download className="w-4 h-4" /> Export</TabsTrigger>
        </TabsList>

        {/* ANALYSIS */}
        <TabsContent value="analysis" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Analysis Configuration</CardTitle>
              <CardDescription>Control how deep the scanner goes into your repository.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label>Scan Depth</Label>
                  <Select 
                    value={settings.analysis?.scan_depth || "deep"} 
                    onValueChange={(v) => updateSection("analysis", "scan_depth", v)}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="shallow">Shallow (Code structures only)</SelectItem>
                      <SelectItem value="deep">Deep (Full AST and metrics)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Analysis Level</Label>
                  <Select 
                    value={settings.analysis?.analysis_level || "thorough"} 
                    onValueChange={(v) => updateSection("analysis", "analysis_level", v)}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="fast">Fast (Skip complex metrics)</SelectItem>
                      <SelectItem value="thorough">Thorough (Include logic checks)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Max Files Limit</Label>
                  <Input 
                    type="number" 
                    value={settings.analysis?.max_files || 2000} 
                    onChange={(e) => updateSection("analysis", "max_files", parseInt(e.target.value))}
                  />
                  <p className="text-xs text-muted-foreground">Stop scanning after this many files</p>
                </div>
                <div className="space-y-2">
                  <Label>Min File Lines</Label>
                  <Input 
                    type="number" 
                    value={settings.analysis?.min_file_lines || 1} 
                    onChange={(e) => updateSection("analysis", "min_file_lines", parseInt(e.target.value))}
                  />
                </div>
                <div className="col-span-2 space-y-2">
                  <Label>Ignored Patterns (Comma separated)</Label>
                  <Input 
                    value={(settings.analysis?.ignored_patterns || []).join(", ")} 
                    onChange={(e) => updateSection("analysis", "ignored_patterns", e.target.value.split(",").map(s => s.trim()))}
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* SECURITY */}
        <TabsContent value="security" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Security Rules</CardTitle>
              <CardDescription>Enable or disable specific security checks during the scan.</CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-4">
              {Object.entries(settings.security || {}).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between p-3 rounded-lg border border-border bg-secondary/10">
                  <Label htmlFor={key} className="flex-1 cursor-pointer">{key.replace("detect_", "").split("_").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")}</Label>
                  <Switch 
                    id={key} 
                    checked={value as boolean} 
                    onCheckedChange={(c) => updateSection("security", key, c)} 
                  />
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        {/* AI */}
        <TabsContent value="ai" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>AI Model Configuration</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2 max-w-md">
                <Label>Language Model</Label>
                <Select 
                  value={settings.ai?.model || "microsoft/codebert-base"} 
                  onValueChange={(v) => updateSection("ai", "model", v)}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="microsoft/codebert-base">CodeBERT (Base)</SelectItem>
                    <SelectItem value="Salesforce/codet5-base">CodeT5 (Base)</SelectItem>
                    <SelectItem value="dummy">Dummy Heuristic Engine</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-4">
                <div className="flex items-center justify-between py-2 border-b">
                  <Label>Generate Suggestions</Label>
                  <Switch checked={settings.ai?.generate_suggestions} onCheckedChange={(c) => updateSection("ai", "generate_suggestions", c)} />
                </div>
                <div className="flex items-center justify-between py-2 border-b">
                  <Label>Generate Explanations</Label>
                  <Switch checked={settings.ai?.generate_explanations} onCheckedChange={(c) => updateSection("ai", "generate_explanations", c)} />
                </div>
                <div className="flex items-center justify-between py-2 border-b">
                  <Label>Generate Improved Code (Auto-Refactor)</Label>
                  <Switch checked={settings.ai?.generate_improved_code} onCheckedChange={(c) => updateSection("ai", "generate_improved_code", c)} />
                </div>
                <div className="flex items-center justify-between py-2">
                  <Label>Max Suggestions Per File</Label>
                  <Input 
                    type="number" 
                    className="w-24"
                    value={settings.ai?.max_suggestions_per_file || 5} 
                    onChange={(e) => updateSection("ai", "max_suggestions_per_file", parseInt(e.target.value))}
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* PERFORMANCE */}
        <TabsContent value="performance" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Performance Tuning</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between p-3 rounded-lg border">
                <div>
                  <Label>Parallel Analysis</Label>
                  <p className="text-xs text-muted-foreground mt-1">Use multiprocess pool for faster parsing</p>
                </div>
                <Switch checked={settings.performance?.parallel_analysis} onCheckedChange={(c) => updateSection("performance", "parallel_analysis", c)} />
              </div>
              <div className="flex items-center justify-between p-3 rounded-lg border">
                <div>
                  <Label>Cache AST Results</Label>
                  <p className="text-xs text-muted-foreground mt-1">Speed up repeat scans</p>
                </div>
                <Switch checked={settings.performance?.cache_results} onCheckedChange={(c) => updateSection("performance", "cache_results", c)} />
              </div>
              <div className="flex items-center justify-between p-3 rounded-lg border">
                <Label>Analysis Timeout (seconds)</Label>
                <Input 
                  type="number" 
                  className="w-24"
                  value={settings.performance?.timeout_seconds || 300} 
                  onChange={(e) => updateSection("performance", "timeout_seconds", parseInt(e.target.value))}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* UI */}
        <TabsContent value="ui" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Interface Preferences</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between p-3 rounded-lg border">
                <Label>Chart Animations</Label>
                <Switch checked={settings.ui?.chart_animations} onCheckedChange={(c) => updateSection("ui", "chart_animations", c)} />
              </div>
              <div className="flex items-center justify-between p-3 rounded-lg border">
                <Label>Show Line Numbers in Editor</Label>
                <Switch checked={settings.ui?.show_line_numbers} onCheckedChange={(c) => updateSection("ui", "show_line_numbers", c)} />
              </div>
              <div className="flex items-center justify-between p-3 rounded-lg border">
                <Label>Default Code Tab</Label>
                <Select 
                  value={settings.ui?.default_code_tab || "original"} 
                  onValueChange={(v) => updateSection("ui", "default_code_tab", v)}
                >
                  <SelectTrigger className="w-[180px]"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="original">Original Code</SelectItem>
                    <SelectItem value="improved">Improved Code</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* EXPORT */}
        <TabsContent value="export" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Export Options</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between p-3 rounded-lg border">
                <Label>Default Format</Label>
                <Select 
                  value={settings.export?.default_format || "json"} 
                  onValueChange={(v) => updateSection("export", "default_format", v)}
                >
                  <SelectTrigger className="w-[180px]"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="json">JSON</SelectItem>
                    <SelectItem value="pdf">PDF Report</SelectItem>
                    <SelectItem value="html">HTML Dashboard</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center justify-between p-3 rounded-lg border">
                <Label>Include Source Code</Label>
                <Switch checked={settings.export?.include_source_code} onCheckedChange={(c) => updateSection("export", "include_source_code", c)} />
              </div>
              <div className="flex items-center justify-between p-3 rounded-lg border">
                <Label>Include Suggested Patches</Label>
                <Switch checked={settings.export?.include_patches} onCheckedChange={(c) => updateSection("export", "include_patches", c)} />
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
