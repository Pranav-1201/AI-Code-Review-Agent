import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Settings as SettingsIcon } from "lucide-react";

export default function SettingsPage() {
  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground mt-1">Configure your AI Code Review Agent</p>
      </div>

      <Card className="bg-card border-border/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <SettingsIcon className="w-5 h-5 text-muted-foreground" />
            General Settings
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4 text-sm text-muted-foreground">
            <p>Settings page coming soon. This will include:</p>
            <ul className="list-disc list-inside space-y-1">
              <li>API endpoint configuration</li>
              <li>LLM model selection</li>
              <li>Analysis depth preferences</li>
              <li>Notification settings</li>
              <li>Theme customization</li>
            </ul>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
