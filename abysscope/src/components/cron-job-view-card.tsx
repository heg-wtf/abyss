"use client";

import {
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { CronJob } from "@/lib/abyss";
import { isOneShot } from "./cron-helpers";

export function JobViewCard({ job }: { job: CronJob }) {
  return (
    <>
      <CardHeader className="pb-2">
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
        <CardDescription className="font-mono text-xs">
          {isOneShot(job) ? `at: ${job.at}` : job.schedule}
          {job.timezone && ` (${job.timezone})`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm whitespace-pre-wrap">{job.message}</p>
        <div className="flex flex-wrap gap-1 mt-2">
          {job.model && (
            <Badge variant="outline" className="text-xs">
              {job.model}
            </Badge>
          )}
          {job.skills?.map((skill) => (
            <Badge key={skill} variant="secondary" className="text-xs">
              {skill}
            </Badge>
          ))}
        </div>
      </CardContent>
    </>
  );
}
