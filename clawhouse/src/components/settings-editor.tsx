"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface GlobalConfig {
  bots: { name: string; path: string }[];
  timezone: string;
  language: string;
  settings: {
    command_timeout: number;
    log_level: string;
  };
}

export function SettingsEditor({
  initialConfig,
}: {
  initialConfig: GlobalConfig;
}) {
  const [config, setConfig] = useState(initialConfig);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    await fetch("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
    setSaving(false);
    setSaved(true);
    setEditing(false);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">General</CardTitle>
          <div className="flex items-center gap-2">
            {saved && <span className="text-sm text-green-600">Saved!</span>}
            {editing ? (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setConfig(initialConfig);
                    setEditing(false);
                  }}
                >
                  Cancel
                </Button>
                <Button size="sm" onClick={handleSave} disabled={saving}>
                  {saving ? "Saving..." : "Save"}
                </Button>
              </>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setEditing(true)}
              >
                Edit
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {editing ? (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Timezone</Label>
              <Input
                value={config.timezone}
                onChange={(e) =>
                  setConfig({ ...config, timezone: e.target.value })
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Language</Label>
              <Input
                value={config.language}
                onChange={(e) =>
                  setConfig({ ...config, language: e.target.value })
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Log Level</Label>
              <Select
                value={config.settings?.log_level || "INFO"}
                onValueChange={(value) => {
                  if (value)
                    setConfig({
                      ...config,
                      settings: { ...config.settings, log_level: value },
                    });
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="DEBUG">DEBUG</SelectItem>
                  <SelectItem value="INFO">INFO</SelectItem>
                  <SelectItem value="WARNING">WARNING</SelectItem>
                  <SelectItem value="ERROR">ERROR</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Command Timeout (seconds)</Label>
              <Input
                type="number"
                value={config.settings?.command_timeout || 300}
                onChange={(e) =>
                  setConfig({
                    ...config,
                    settings: {
                      ...config.settings,
                      command_timeout: parseInt(e.target.value, 10) || 300,
                    },
                  })
                }
              />
            </div>
          </div>
        ) : (
          <>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Timezone</span>
              <span className="font-mono">{config.timezone}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Language</span>
              <span>{config.language}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Log Level</span>
              <span className="font-mono">
                {config.settings?.log_level || "INFO"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Command Timeout</span>
              <span className="font-mono">
                {config.settings?.command_timeout || 300}s
              </span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
