"use client";

import {
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import type { CronJob } from "@/lib/abyss";
import { isOneShot } from "./cron-helpers";

export function JobEditForm({
  job,
  index,
  availableSkills,
  onUpdate,
  onDone,
  onRemove,
}: {
  job: CronJob;
  index: number;
  availableSkills: string[];
  onUpdate: (index: number, updates: Partial<CronJob>) => void;
  onDone: () => void;
  onRemove: (index: number) => void;
}) {
  const oneShot = isOneShot(job);

  const toggleJobType = () => {
    if (oneShot) {
      onUpdate(index, {
        ...job,
        schedule: "0 9 * * *",
        at: undefined,
        delete_after_run: undefined,
      });
    } else {
      onUpdate(index, { ...job, schedule: undefined, at: "" });
    }
  };

  const toggleSkill = (skill: string) => {
    const current = job.skills || [];
    const updated = current.includes(skill)
      ? current.filter((s) => s !== skill)
      : [...current, skill];
    onUpdate(index, { skills: updated.length > 0 ? updated : undefined });
  };

  return (
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
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={onDone}>
              Done
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onRemove(index)}
              className="text-destructive"
            >
              Remove
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-4">
          <Label className="text-xs text-muted-foreground">Type</Label>
          <div className="flex items-center gap-2">
            <Button
              variant={oneShot ? "outline" : "default"}
              size="sm"
              onClick={() => {
                if (oneShot) toggleJobType();
              }}
            >
              Recurring
            </Button>
            <Button
              variant={oneShot ? "default" : "outline"}
              size="sm"
              onClick={() => {
                if (!oneShot) toggleJobType();
              }}
            >
              One-shot
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Name</Label>
            <Input
              value={job.name}
              onChange={(e) => onUpdate(index, { name: e.target.value })}
            />
          </div>
          {oneShot ? (
            <div className="space-y-2">
              <Label>At (ISO datetime or duration)</Label>
              <Input
                value={job.at || ""}
                onChange={(e) => onUpdate(index, { at: e.target.value })}
                placeholder="2026-03-25T15:00:00 or 30m"
                className="font-mono"
              />
            </div>
          ) : (
            <div className="space-y-2">
              <Label>Schedule (cron)</Label>
              <Input
                value={job.schedule || ""}
                onChange={(e) => onUpdate(index, { schedule: e.target.value })}
                placeholder="0 9 * * *"
                className="font-mono"
              />
            </div>
          )}
        </div>

        <div className="space-y-2">
          <Label>Model (optional)</Label>
          <Input
            value={job.model || ""}
            onChange={(e) =>
              onUpdate(index, { model: e.target.value || undefined })
            }
            placeholder="sonnet"
          />
        </div>

        <div className="space-y-2">
          <Label>Message</Label>
          <Textarea
            rows={4}
            value={job.message}
            onChange={(e) => onUpdate(index, { message: e.target.value })}
          />
        </div>

        {availableSkills.length > 0 && (
          <div className="space-y-2">
            <Label>Skills</Label>
            <div className="flex flex-wrap gap-1">
              {availableSkills.map((skill) => (
                <Badge
                  key={skill}
                  variant={
                    (job.skills || []).includes(skill) ? "default" : "outline"
                  }
                  className="cursor-pointer text-xs"
                  onClick={() => toggleSkill(skill)}
                >
                  {skill}
                </Badge>
              ))}
            </div>
          </div>
        )}

        <div className="flex items-center justify-between">
          <Label>Enabled</Label>
          <Switch
            checked={job.enabled}
            onCheckedChange={(checked) => onUpdate(index, { enabled: checked })}
          />
        </div>

        {oneShot && (
          <div className="flex items-center justify-between">
            <Label>Delete after run</Label>
            <Switch
              checked={job.delete_after_run || false}
              onCheckedChange={(checked) =>
                onUpdate(index, { delete_after_run: checked || undefined })
              }
            />
          </div>
        )}
      </CardContent>
    </>
  );
}
