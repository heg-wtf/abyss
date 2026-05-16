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

const TIMEZONES = [
  { value: "Asia/Seoul", label: "Asia/Seoul" },
  { value: "Asia/Tokyo", label: "Asia/Tokyo" },
  { value: "Asia/Shanghai", label: "Asia/Shanghai" },
  { value: "Asia/Singapore", label: "Asia/Singapore" },
  { value: "Asia/Kolkata", label: "Asia/Kolkata" },
  { value: "Asia/Dubai", label: "Asia/Dubai" },
  { value: "Europe/London", label: "Europe/London" },
  { value: "Europe/Paris", label: "Europe/Paris" },
  { value: "Europe/Berlin", label: "Europe/Berlin" },
  { value: "America/New_York", label: "America/New_York" },
  { value: "America/Chicago", label: "America/Chicago" },
  { value: "America/Denver", label: "America/Denver" },
  { value: "America/Los_Angeles", label: "America/Los_Angeles" },
  { value: "America/Sao_Paulo", label: "America/Sao_Paulo" },
  { value: "Australia/Sydney", label: "Australia/Sydney" },
  { value: "Pacific/Auckland", label: "Pacific/Auckland" },
  { value: "UTC", label: "UTC" },
];

const LANGUAGES = [
  { value: "Korean", label: "Korean" },
  { value: "English", label: "English" },
  { value: "Japanese", label: "Japanese" },
  { value: "Chinese", label: "Chinese" },
];

interface GlobalConfig {
  bots: { name: string; path: string }[];
  timezone: string;
  language: string;
  elevenlabs_api_key?: string;
  settings: {
    command_timeout: number;
    log_level: string;
  };
}

function maskKey(key: string | undefined): string {
  if (!key) return "—";
  if (key.length <= 8) return "•".repeat(key.length);
  return `${key.slice(0, 4)}${"•".repeat(Math.max(key.length - 8, 4))}${key.slice(-4)}`;
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
              <Select
                value={config.timezone}
                onValueChange={(value) => {
                  if (value) setConfig({ ...config, timezone: value });
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIMEZONES.map((timezone) => (
                    <SelectItem key={timezone.value} value={timezone.value}>
                      {timezone.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Language</Label>
              <Select
                value={config.language}
                onValueChange={(value) => {
                  if (value) setConfig({ ...config, language: value });
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LANGUAGES.map((language) => (
                    <SelectItem key={language.value} value={language.value}>
                      {language.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
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
            <div className="space-y-2">
              <Label>ElevenLabs API Key</Label>
              <Input
                type="password"
                autoComplete="off"
                placeholder="sk_..."
                value={config.elevenlabs_api_key || ""}
                onChange={(e) =>
                  setConfig({
                    ...config,
                    elevenlabs_api_key: e.target.value,
                  })
                }
              />
              <p className="text-xs text-muted-foreground">
                Used for voice mode STT (Scribe v2) and TTS (Flash v2.5). Restart
                abyss after changing.
              </p>
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
            <div className="flex justify-between">
              <span className="text-muted-foreground">ElevenLabs API Key</span>
              <span className="font-mono">
                {maskKey(config.elevenlabs_api_key)}
              </span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
