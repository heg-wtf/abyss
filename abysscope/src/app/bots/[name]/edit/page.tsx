"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AvatarUploader } from "@/components/bots/avatar-uploader";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface BotFormData {
  display_name: string;
  personality: string;
  role: string;
  goal: string;
  model: string;
  streaming: boolean;
  command_timeout?: number;
  skills: string[];
  heartbeat?: {
    enabled: boolean;
    interval_minutes: number;
    active_hours: {
      start: string;
      end: string;
    };
  };
}

export default function BotEditPage() {
  const params = useParams();
  const router = useRouter();
  const name = params.name as string;

  const [form, setForm] = useState<BotFormData | null>(null);
  const [availableSkills, setAvailableSkills] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    Promise.all([
      fetch(`/api/bots/${name}`).then((r) => r.json()),
      fetch("/api/skills").then((r) => r.json()),
    ]).then(([bot, skills]) => {
      setForm({
        display_name: bot.display_name || "",
        personality: bot.personality || "",
        role: bot.role || "",
        goal: bot.goal || "",
        model: bot.model || "sonnet",
        streaming: bot.streaming || false,
        command_timeout: bot.command_timeout,
        skills: bot.skills || [],
        heartbeat: bot.heartbeat || {
          enabled: false,
          interval_minutes: 30,
          active_hours: { start: "07:00", end: "23:00" },
        },
      });
      setAvailableSkills(skills.map((s: { name: string }) => s.name));
    });
  }, [name]);

  const handleSave = async () => {
    if (!form) return;
    setSaving(true);
    await fetch(`/api/bots/${name}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const toggleSkill = (skill: string) => {
    if (!form) return;
    const skills = form.skills.includes(skill)
      ? form.skills.filter((s) => s !== skill)
      : [...form.skills, skill];
    setForm({ ...form, skills });
  };

  if (!form) return <p className="text-sm text-muted-foreground">Loading...</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href={`/bots/${name}`}
            className="text-muted-foreground hover:text-foreground text-sm"
          >
            {form.display_name || name}
          </Link>
          <span className="text-muted-foreground">/</span>
          <h1 className="text-2xl font-bold">Edit</h1>
        </div>
        <div className="flex items-center gap-2">
          {saved && <span className="text-sm text-green-600">Saved!</span>}
          <Button
            variant="outline"
            onClick={() => router.push(`/bots/${name}`)}
          >
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : "Save"}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Basic Info</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Display Name</Label>
              <Input
                value={form.display_name}
                onChange={(e) =>
                  setForm({ ...form, display_name: e.target.value })
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Avatar</Label>
              <AvatarUploader botName={name} />
            </div>
            <div className="space-y-2">
              <Label>Model</Label>
              <Select
                value={form.model}
                onValueChange={(value) => {
                  if (value) setForm({ ...form, model: value });
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="opus">Opus</SelectItem>
                  <SelectItem value="sonnet">Sonnet</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between">
              <Label>Streaming</Label>
              <Switch
                checked={form.streaming}
                onCheckedChange={(checked) =>
                  setForm({ ...form, streaming: checked })
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Command Timeout (seconds)</Label>
              <Input
                type="number"
                value={form.command_timeout || ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    command_timeout: e.target.value
                      ? parseInt(e.target.value, 10)
                      : undefined,
                  })
                }
                placeholder="Default: 300"
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Skills</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {availableSkills.map((skill) => (
                <button
                  key={skill}
                  onClick={() => toggleSkill(skill)}
                  className={`inline-flex items-center rounded-md px-2.5 py-0.5 text-xs font-medium transition-colors border cursor-pointer ${
                    form.skills.includes(skill)
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-background text-muted-foreground border-border hover:bg-accent"
                  }`}
                >
                  {skill}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Personality</CardTitle>
        </CardHeader>
        <CardContent>
          <Textarea
            rows={4}
            value={form.personality}
            onChange={(e) => setForm({ ...form, personality: e.target.value })}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Role</CardTitle>
        </CardHeader>
        <CardContent>
          <Textarea
            rows={4}
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Goal</CardTitle>
        </CardHeader>
        <CardContent>
          <Textarea
            rows={3}
            value={form.goal}
            onChange={(e) => setForm({ ...form, goal: e.target.value })}
          />
        </CardContent>
      </Card>

      {form.heartbeat && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Heartbeat</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <Label>Enabled</Label>
              <Switch
                checked={form.heartbeat.enabled}
                onCheckedChange={(checked) =>
                  setForm({
                    ...form,
                    heartbeat: { ...form.heartbeat!, enabled: checked },
                  })
                }
              />
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>Interval (min)</Label>
                <Input
                  type="number"
                  value={form.heartbeat.interval_minutes}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      heartbeat: {
                        ...form.heartbeat!,
                        interval_minutes: parseInt(e.target.value, 10) || 30,
                      },
                    })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label>Start</Label>
                <Input
                  value={form.heartbeat.active_hours.start}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      heartbeat: {
                        ...form.heartbeat!,
                        active_hours: {
                          ...form.heartbeat!.active_hours,
                          start: e.target.value,
                        },
                      },
                    })
                  }
                  placeholder="07:00"
                />
              </div>
              <div className="space-y-2">
                <Label>End</Label>
                <Input
                  value={form.heartbeat.active_hours.end}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      heartbeat: {
                        ...form.heartbeat!,
                        active_hours: {
                          ...form.heartbeat!.active_hours,
                          end: e.target.value,
                        },
                      },
                    })
                  }
                  placeholder="23:00"
                />
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
