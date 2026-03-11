"use client";

import { useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";

interface CronJob {
  name: string;
  enabled: boolean;
  schedule: string;
  message: string;
  timezone?: string;
  model?: string;
  skills?: string[];
}

interface CronEditorProps {
  botName: string;
  initialJobs: CronJob[];
}

export function CronEditor({ botName, initialJobs }: CronEditorProps) {
  const [jobs, setJobs] = useState<CronJob[]>(initialJobs);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    await fetch(`/api/bots/${botName}/cron`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jobs }),
    });
    setSaving(false);
    setSaved(true);
    setEditingIndex(null);
    setTimeout(() => setSaved(false), 2000);
  };

  const addJob = () => {
    const newJob: CronJob = {
      name: `job-${jobs.length + 1}`,
      enabled: true,
      schedule: "0 9 * * *",
      message: "",
      timezone: "Asia/Seoul",
    };
    setJobs([...jobs, newJob]);
    setEditingIndex(jobs.length);
  };

  const removeJob = (index: number) => {
    setJobs(jobs.filter((_, i) => i !== index));
    setEditingIndex(null);
  };

  const updateJob = (index: number, updates: Partial<CronJob>) => {
    setJobs(jobs.map((j, i) => (i === index ? { ...j, ...updates } : j)));
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {saved && <span className="text-sm text-green-600">Saved!</span>}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={addJob}>
            Add Job
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : "Save All"}
          </Button>
        </div>
      </div>

      {jobs.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No cron jobs. Click &quot;Add Job&quot; to create one.
        </p>
      ) : (
        jobs.map((job, index) => (
          <Card key={index}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-sm">{job.name}</CardTitle>
                  <Badge
                    variant={job.enabled ? "default" : "secondary"}
                    className="text-xs"
                  >
                    {job.enabled ? "Active" : "Disabled"}
                  </Badge>
                </div>
                <div className="flex items-center gap-2">
                  {editingIndex === index ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setEditingIndex(null)}
                    >
                      Done
                    </Button>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setEditingIndex(index)}
                    >
                      Edit
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => removeJob(index)}
                    className="text-destructive"
                  >
                    Remove
                  </Button>
                </div>
              </div>
              {editingIndex !== index && (
                <CardDescription className="font-mono text-xs">
                  {job.schedule}
                  {job.timezone && ` (${job.timezone})`}
                </CardDescription>
              )}
            </CardHeader>
            {editingIndex === index ? (
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Name</Label>
                    <Input
                      value={job.name}
                      onChange={(e) =>
                        updateJob(index, { name: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Schedule (cron)</Label>
                    <Input
                      value={job.schedule}
                      onChange={(e) =>
                        updateJob(index, { schedule: e.target.value })
                      }
                      placeholder="0 9 * * *"
                      className="font-mono"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Timezone</Label>
                    <Input
                      value={job.timezone || ""}
                      onChange={(e) =>
                        updateJob(index, { timezone: e.target.value })
                      }
                      placeholder="Asia/Seoul"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Model (optional)</Label>
                    <Input
                      value={job.model || ""}
                      onChange={(e) =>
                        updateJob(index, {
                          model: e.target.value || undefined,
                        })
                      }
                      placeholder="sonnet"
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>Message</Label>
                  <Textarea
                    rows={3}
                    value={job.message}
                    onChange={(e) =>
                      updateJob(index, { message: e.target.value })
                    }
                  />
                </div>
                <div className="flex items-center justify-between">
                  <Label>Enabled</Label>
                  <Switch
                    checked={job.enabled}
                    onCheckedChange={(checked) =>
                      updateJob(index, { enabled: checked })
                    }
                  />
                </div>
              </CardContent>
            ) : (
              <CardContent>
                <p className="text-sm">{job.message}</p>
              </CardContent>
            )}
          </Card>
        ))
      )}
    </div>
  );
}
