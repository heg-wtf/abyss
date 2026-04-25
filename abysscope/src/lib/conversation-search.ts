import fs from "fs";
import path from "path";
import { spawn } from "node:child_process";
import { DatabaseSync } from "node:sqlite";
import { getConfig, getAbyssHome } from "@/lib/abyss";

export interface SearchHit {
  ts: string;
  role: string;
  chatId: string;
  dateKey: string;
  snippet: string;
}

export interface SearchStatus {
  available: boolean;
  fts5Available: boolean;
  dbPath: string;
  dbExists: boolean;
  dbSize: number;
  messageCount: number;
  oldestTs: string | null;
  newestTs: string | null;
}

export interface ReindexResult {
  ok: boolean;
  count: number;
  output: string;
  error?: string;
}

function botPathFor(name: string): string | null {
  const config = getConfig();
  if (!config) return null;
  const entry = config.bots?.find((b) => b.name === name);
  if (!entry) return null;
  return entry.path.startsWith("/")
    ? entry.path
    : path.join(getAbyssHome(), entry.path);
}

export function botDbPath(name: string): string | null {
  const botPath = botPathFor(name);
  if (!botPath) return null;
  return path.join(botPath, "conversation.db");
}

function checkFts5(): boolean {
  try {
    const db = new DatabaseSync(":memory:");
    db.exec("CREATE VIRTUAL TABLE _t USING fts5(c)");
    db.close();
    return true;
  } catch {
    return false;
  }
}

export function getSearchStatus(botName: string): SearchStatus {
  const dbPath = botDbPath(botName);
  const fts5Available = checkFts5();
  const empty: SearchStatus = {
    available: false,
    fts5Available,
    dbPath: dbPath ?? "",
    dbExists: false,
    dbSize: 0,
    messageCount: 0,
    oldestTs: null,
    newestTs: null,
  };

  if (!dbPath) return empty;
  if (!fs.existsSync(dbPath)) {
    return { ...empty, dbPath };
  }
  const stat = fs.statSync(dbPath);
  let messageCount = 0;
  let oldestTs: string | null = null;
  let newestTs: string | null = null;
  try {
    const db = new DatabaseSync(dbPath, { readOnly: true });
    const row = db
      .prepare(
        "SELECT COUNT(*) AS c, MIN(ts) AS oldest, MAX(ts) AS newest FROM messages",
      )
      .get() as
      | { c: number; oldest: string | null; newest: string | null }
      | undefined;
    if (row) {
      messageCount = Number(row.c ?? 0);
      oldestTs = row.oldest ?? null;
      newestTs = row.newest ?? null;
    }
    db.close();
  } catch {
    return { ...empty, dbPath, dbExists: true, dbSize: stat.size };
  }
  return {
    available: fts5Available,
    fts5Available,
    dbPath,
    dbExists: true,
    dbSize: stat.size,
    messageCount,
    oldestTs,
    newestTs,
  };
}

function escapeFtsQuery(query: string): string {
  // FTS5 MATCH expects a string; wrap user input as a phrase to neutralise
  // operators while keeping unicode tokenisation. Escape embedded quotes.
  const trimmed = query.trim();
  if (!trimmed) return "";
  const escaped = trimmed.replace(/"/g, '""');
  return `"${escaped}"`;
}

export function searchMessages(
  botName: string,
  query: string,
  limit = 30,
): SearchHit[] {
  const dbPath = botDbPath(botName);
  if (!dbPath || !fs.existsSync(dbPath)) return [];
  const ftsQuery = escapeFtsQuery(query);
  if (!ftsQuery) return [];
  const safeLimit = Math.min(Math.max(limit, 1), 100);
  const db = new DatabaseSync(dbPath, { readOnly: true });
  try {
    const rows = db
      .prepare(
        `SELECT ts, role, chat_id AS chatId, date_key AS dateKey,
                snippet(messages, 0, '<<', '>>', '…', 12) AS snippet
         FROM messages
         WHERE messages MATCH ?
         ORDER BY ts DESC
         LIMIT ?`,
      )
      .all(ftsQuery, safeLimit) as SearchHit[];
    return rows.map((r) => ({
      ts: String(r.ts ?? ""),
      role: String(r.role ?? ""),
      chatId: String(r.chatId ?? ""),
      dateKey: String(r.dateKey ?? ""),
      snippet: String(r.snippet ?? ""),
    }));
  } finally {
    db.close();
  }
}

export async function reindexBot(botName: string): Promise<ReindexResult> {
  return new Promise((resolve) => {
    const proc = spawn("abyss", ["reindex", "--bot", botName], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (chunk) => (stdout += chunk.toString()));
    proc.stderr.on("data", (chunk) => (stderr += chunk.toString()));
    proc.on("error", (err) => {
      resolve({
        ok: false,
        count: 0,
        output: stdout + stderr,
        error: err.message,
      });
    });
    proc.on("close", (code) => {
      const combined = stdout + stderr;
      const match = combined.match(/indexed\s+(\d+)\s+message/i);
      const count = match ? Number(match[1]) : 0;
      resolve({
        ok: code === 0,
        count,
        output: combined,
        error: code === 0 ? undefined : `exit code ${code}`,
      });
    });
  });
}
