import fs from "fs";
import path from "path";
import { abyssPath, getAbyssHome } from "./paths";

export interface SystemStatus {
  running: boolean;
  pid: number | null;
  uptime: string | null;
}

export interface DiskUsage {
  totalBytes: number;
  totalFormatted: string;
  breakdown: { name: string; bytes: number; formatted: string }[];
}

export function getSystemStatus(): SystemStatus {
  const pidPath = abyssPath("abyss.pid");
  try {
    const pidStr = fs.readFileSync(pidPath, "utf-8").trim();
    const pid = parseInt(pidStr, 10);
    try {
      process.kill(pid, 0);
      return { running: true, pid, uptime: null };
    } catch {
      return { running: false, pid: null, uptime: null };
    }
  } catch {
    return { running: false, pid: null, uptime: null };
  }
}

function getDirectorySize(dirPath: string): number {
  let total = 0;
  try {
    const entries = fs.readdirSync(dirPath, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dirPath, entry.name);
      if (entry.isDirectory()) {
        total += getDirectorySize(fullPath);
      } else if (entry.isFile()) {
        try {
          total += fs.statSync(fullPath).size;
        } catch {
          // skip inaccessible files
        }
      }
    }
  } catch {
    // skip inaccessible directories
  }
  return total;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function getDiskUsage(): DiskUsage {
  const breakdown: { name: string; bytes: number; formatted: string }[] = [];

  try {
    const entries = fs.readdirSync(getAbyssHome(), { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(getAbyssHome(), entry.name);
      let bytes = 0;
      if (entry.isDirectory()) {
        bytes = getDirectorySize(fullPath);
      } else if (entry.isFile()) {
        try {
          bytes = fs.statSync(fullPath).size;
        } catch {
          continue;
        }
      }
      breakdown.push({
        name: entry.name,
        bytes,
        formatted: formatBytes(bytes),
      });
    }
  } catch {
    // ~/.abyss not found
  }

  breakdown.sort((a, b) => b.bytes - a.bytes);
  const totalBytes = breakdown.reduce((sum, item) => sum + item.bytes, 0);

  return {
    totalBytes,
    totalFormatted: formatBytes(totalBytes),
    breakdown,
  };
}
