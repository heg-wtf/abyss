import fs from "fs";
import path from "path";
import { abyssPath } from "./paths";
import { getBotPath, listBots } from "./bots";

export interface ToolMetricEvent {
  ts: string;
  tool: string;
  duration_ms: number;
  exit_code?: number;
  session_id?: string;
  outcome?: "success" | "failure";
}

export interface ToolMetricRow {
  tool: string;
  count: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  errorCount: number;
}

export interface BotConversationFrequency {
  botName: string;
  displayName: string;
  data: Record<string, number>; // ISO date (YYYY-MM-DD) → user message count
  total: number;
}

function percentile(sorted: number[], pct: number): number {
  if (sorted.length === 0) return 0;
  if (pct <= 0) return sorted[0];
  if (pct >= 100) return sorted[sorted.length - 1];
  const rank = (pct / 100) * (sorted.length - 1);
  const lower = Math.floor(rank);
  const upper = Math.min(lower + 1, sorted.length - 1);
  const fraction = rank - lower;
  return sorted[lower] + (sorted[upper] - sorted[lower]) * fraction;
}

/**
 * Iterate every event recorded in `tool_metrics/*.jsonl` for a bot.
 * Returns events in oldest-first order (filenames are YYYYMMDD).
 */
export function readToolMetricEvents(name: string): ToolMetricEvent[] {
  const botPath = getBotPath(name);
  if (!botPath) return [];
  const metricsDir = path.join(botPath, "tool_metrics");
  if (!fs.existsSync(metricsDir)) return [];

  const events: ToolMetricEvent[] = [];
  let entries: string[] = [];
  try {
    entries = fs.readdirSync(metricsDir).sort();
  } catch {
    return [];
  }
  for (const entry of entries) {
    if (!entry.endsWith(".jsonl")) continue;
    const filePath = path.join(metricsDir, entry);
    let raw: string;
    try {
      raw = fs.readFileSync(filePath, "utf-8");
    } catch {
      continue;
    }
    for (const line of raw.split("\n")) {
      if (!line.trim()) continue;
      try {
        const parsed = JSON.parse(line);
        if (parsed && typeof parsed.tool === "string"
            && typeof parsed.duration_ms === "number") {
          events.push(parsed as ToolMetricEvent);
        }
      } catch {
        // ignore malformed line
      }
    }
  }
  return events;
}

export function getToolMetrics(name: string): ToolMetricRow[] {
  const events = readToolMetricEvents(name);
  if (events.length === 0) return [];

  const buckets: Record<string, number[]> = {};
  const errors: Record<string, number> = {};

  for (const event of events) {
    if (!buckets[event.tool]) {
      buckets[event.tool] = [];
      errors[event.tool] = 0;
    }
    buckets[event.tool].push(event.duration_ms);
    const isFailure =
      event.outcome === "failure"
      || (typeof event.exit_code === "number" && event.exit_code !== 0);
    if (isFailure) {
      errors[event.tool] = (errors[event.tool] ?? 0) + 1;
    }
  }

  const rows: ToolMetricRow[] = Object.entries(buckets).map(
    ([tool, values]) => {
      const sorted = [...values].sort((a, b) => a - b);
      return {
        tool,
        count: sorted.length,
        p50_ms: percentile(sorted, 50),
        p95_ms: percentile(sorted, 95),
        p99_ms: percentile(sorted, 99),
        errorCount: errors[tool] ?? 0,
      };
    },
  );

  rows.sort((a, b) => b.count - a.count);
  return rows;
}

export function getConversationFrequency(): BotConversationFrequency[] {
  const bots = listBots();
  const cutoff = new Date();
  cutoff.setFullYear(cutoff.getFullYear() - 1);

  return bots.map((bot) => {
    const botPath = abyssPath("bots", bot.name);
    const sessionsDir = path.join(botPath, "sessions");
    const data: Record<string, number> = {};

    if (!fs.existsSync(sessionsDir)) {
      return {
        botName: bot.name,
        displayName: bot.display_name || bot.telegram_botname || bot.name,
        data,
        total: 0,
      };
    }

    const sessionDirs = fs.readdirSync(sessionsDir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => path.join(sessionsDir, entry.name));

    for (const sessionDir of sessionDirs) {
      let files: string[];
      try {
        files = fs.readdirSync(sessionDir);
      } catch {
        continue;
      }

      for (const file of files) {
        const match = file.match(/^conversation-(\d{6})\.md$/);
        if (!match) continue;

        const raw = match[1]; // YYMMDD
        const year = 2000 + parseInt(raw.slice(0, 2), 10);
        const month = parseInt(raw.slice(2, 4), 10) - 1;
        const day = parseInt(raw.slice(4, 6), 10);
        const date = new Date(year, month, day);

        if (date < cutoff) continue;

        const isoDate = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        let content = "";
        try {
          content = fs.readFileSync(path.join(sessionDir, file), "utf-8");
        } catch {
          continue;
        }

        const count = (content.match(/^## user/gm) || []).length;
        data[isoDate] = (data[isoDate] || 0) + count;
      }
    }

    const total = Object.values(data).reduce((sum, n) => sum + n, 0);
    return {
      botName: bot.name,
      displayName: bot.display_name || bot.telegram_botname || bot.name,
      data,
      total,
    };
  });
}
