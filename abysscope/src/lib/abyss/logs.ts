import fs from "fs";
import { abyssPath } from "./paths";

export interface DaemonLogInfo {
  name: string;
  size: number;
  exists: boolean;
}

const DAEMON_LOG_FILES = ["daemon-stdout.log", "daemon-stderr.log"];

function isValidLogFilename(filename: string): boolean {
  return /^abyss-\d{6}\.log$/.test(filename);
}

export function listLogFiles(): string[] {
  const logsDir = abyssPath("logs");
  try {
    return fs
      .readdirSync(logsDir)
      .filter((f) => f.startsWith("abyss-") && f.endsWith(".log"))
      .sort()
      .reverse();
  } catch {
    return [];
  }
}

export function getLogContent(
  filename: string,
  offset = 0,
  limit = 500,
): { lines: string[]; totalLines: number } {
  const logPath = abyssPath("logs", filename);
  try {
    const content = fs.readFileSync(logPath, "utf-8");
    const allLines = content.split("\n");
    return {
      lines: allLines.slice(offset, offset + limit),
      totalLines: allLines.length,
    };
  } catch {
    return { lines: [], totalLines: 0 };
  }
}

export function deleteLogFiles(filenames: string[]): number {
  let deleted = 0;
  for (const filename of filenames) {
    if (!isValidLogFilename(filename)) continue;
    const logPath = abyssPath("logs", filename);
    try {
      fs.unlinkSync(logPath);
      deleted++;
    } catch {
      // file already gone
    }
  }
  return deleted;
}

export function getDaemonLogInfo(): DaemonLogInfo[] {
  return DAEMON_LOG_FILES.map((name) => {
    const logPath = abyssPath("logs", name);
    try {
      const stat = fs.statSync(logPath);
      return { name, size: stat.size, exists: true };
    } catch {
      return { name, size: 0, exists: false };
    }
  });
}

export function truncateDaemonLogs(): number {
  let truncated = 0;
  for (const name of DAEMON_LOG_FILES) {
    const logPath = abyssPath("logs", name);
    try {
      fs.writeFileSync(logPath, "");
      truncated++;
    } catch {
      // file doesn't exist
    }
  }
  return truncated;
}
