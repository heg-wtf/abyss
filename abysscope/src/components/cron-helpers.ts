import type { CronJob } from "@/lib/abyss";

export function isOneShot(job: CronJob): boolean {
  return job.at !== undefined;
}
