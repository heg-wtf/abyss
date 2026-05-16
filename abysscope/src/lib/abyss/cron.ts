import path from "path";
import { readYaml, writeYaml } from "./io";
import { getBotPath } from "./bots";

export interface CronJob {
  name: string;
  enabled: boolean;
  schedule?: string;
  message: string;
  timezone?: string;
  model?: string;
  skills?: string[];
  at?: string;
  delete_after_run?: boolean;
}

export function getCronJobs(botName: string): CronJob[] {
  const botPath = getBotPath(botName);
  if (!botPath) return [];
  const cronData = readYaml<{ jobs: CronJob[] }>(
    path.join(botPath, "cron.yaml"),
  );
  return cronData?.jobs || [];
}

export function updateCronJobs(botName: string, jobs: CronJob[]): void {
  const botPath = getBotPath(botName);
  if (!botPath) return;
  writeYaml(path.join(botPath, "cron.yaml"), { jobs });
}
