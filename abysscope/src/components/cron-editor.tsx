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
import { Badge } from "@/components/ui/badge";
import type { CronJob } from "@/lib/abyss";
import { isOneShot } from "./cron-helpers";
import { JobViewCard } from "./cron-job-view-card";
import { JobEditForm } from "./cron-job-edit-form";

interface CronEditorProps {
  botName: string;
  initialJobs: CronJob[];
  availableSkills?: string[];
}
export function CronEditor({
  botName,
  initialJobs,
  availableSkills = [],
}: CronEditorProps) {
  const [jobs, setJobs] = useState<CronJob[]>(initialJobs);
  const [editing, setEditing] = useState(false);
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

  const handleCancel = () => {
    setJobs(initialJobs);
    setEditing(false);
    setEditingIndex(null);
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
          {editing ? (
            <>
              <Button variant="outline" size="sm" onClick={addJob}>
                Add Job
              </Button>
              <Button variant="outline" size="sm" onClick={handleCancel}>
                Cancel
              </Button>
              <Button size="sm" onClick={handleSave} disabled={saving}>
                {saving ? "Saving..." : "Save All"}
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

      {jobs.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No cron jobs configured.
          {editing && ' Click "Add Job" to create one.'}
        </p>
      ) : (
        jobs.map((job, index) => (
          <Card key={index}>
            {editing && editingIndex === index ? (
              <JobEditForm
                job={job}
                index={index}
                availableSkills={availableSkills}
                onUpdate={updateJob}
                onDone={() => setEditingIndex(null)}
                onRemove={removeJob}
              />
            ) : editing ? (
              <>
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
                      {isOneShot(job) && (
                        <Badge variant="outline" className="text-xs">
                          One-shot
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setEditingIndex(index)}
                      >
                        Edit
                      </Button>
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
                  <CardDescription className="font-mono text-xs">
                    {isOneShot(job) ? `at: ${job.at}` : job.schedule}
                    {job.timezone && ` (${job.timezone})`}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-sm">{job.message}</p>
                </CardContent>
              </>
            ) : (
              <JobViewCard job={job} />
            )}
          </Card>
        ))
      )}
    </div>
  );
}
