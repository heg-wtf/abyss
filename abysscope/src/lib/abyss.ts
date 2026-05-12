import fs from "fs";
import path from "path";
import yaml from "js-yaml";

export function getAbyssHome(): string {
  return process.env.ABYSS_HOME || path.join(process.env.HOME || "~", ".abyss");
}

export interface BotConfig {
  name: string;
  telegram_token: string;
  telegram_username: string;
  telegram_botname: string;
  display_name: string;
  personality: string;
  role: string;
  goal: string;
  model: string;
  streaming: boolean;
  skills: string[];
  allowed_users: string[];
  claude_args: string[];
  command_timeout?: number;
  heartbeat?: {
    enabled: boolean;
    interval_minutes: number;
    active_hours: {
      start: string;
      end: string;
    };
  };
}

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

export interface SkillConfig {
  name: string;
  type: "mcp" | "cli";
  status: string;
  description: string;
  emoji?: string;
  allowed_tools: string[];
  environment_variables: string[];
  environment_variable_values: Record<string, string>;
  required_commands: string[];
  install_hints: Record<string, string>;
}

export interface GlobalConfig {
  bots: { name: string; path: string }[];
  timezone: string;
  language: string;
  settings: {
    command_timeout: number;
    log_level: string;
  };
}

export interface SystemStatus {
  running: boolean;
  pid: number | null;
  uptime: string | null;
}

export interface SessionInfo {
  chatId: string;
  lastActivity: Date | null;
  conversationFiles: string[];
  hasSessionId: boolean;
}

function abyssPath(...segments: string[]): string {
  return path.join(getAbyssHome(), ...segments);
}

function readYaml<T>(filePath: string): T | null {
  try {
    const content = fs.readFileSync(filePath, "utf-8");
    return yaml.load(content) as T;
  } catch {
    return null;
  }
}

function writeYaml(filePath: string, data: unknown): void {
  const content = yaml.dump(data, {
    lineWidth: 100,
    noRefs: true,
    quotingType: "'",
    forceQuotes: false,
  });
  fs.writeFileSync(filePath, content, "utf-8");
}

function readMarkdown(filePath: string): string {
  try {
    return fs.readFileSync(filePath, "utf-8");
  } catch {
    return "";
  }
}

function writeMarkdown(filePath: string, content: string): void {
  fs.writeFileSync(filePath, content, "utf-8");
}

// --- Config ---

export function getConfig(): GlobalConfig | null {
  return readYaml<GlobalConfig>(abyssPath("config.yaml"));
}

export function updateConfig(config: GlobalConfig): void {
  writeYaml(abyssPath("config.yaml"), config);
}

// --- Bots ---

export function listBots(): BotConfig[] {
  const config = getConfig();
  if (!config) return [];

  return config.bots
    .map((botEntry) => {
      const botPath = botEntry.path.startsWith("/")
        ? botEntry.path
        : abyssPath(botEntry.path);
      const botYaml = readYaml<Omit<BotConfig, "name">>(
        path.join(botPath, "bot.yaml"),
      );
      if (!botYaml) return null;
      return { ...botYaml, name: botEntry.name } as BotConfig;
    })
    .filter((b): b is BotConfig => b !== null);
}

export function getBot(name: string): BotConfig | null {
  const config = getConfig();
  if (!config) return null;

  const botEntry = config.bots.find((b) => b.name === name);
  if (!botEntry) return null;

  const botPath = botEntry.path.startsWith("/")
    ? botEntry.path
    : abyssPath(botEntry.path);
  const botYaml = readYaml<Omit<BotConfig, "name">>(
    path.join(botPath, "bot.yaml"),
  );
  if (!botYaml) return null;
  return { ...botYaml, name } as BotConfig;
}

export function updateBot(name: string, updates: Partial<BotConfig>): void {
  const config = getConfig();
  if (!config) return;

  const botEntry = config.bots.find((b) => b.name === name);
  if (!botEntry) return;

  const botPath = botEntry.path.startsWith("/")
    ? botEntry.path
    : abyssPath(botEntry.path);
  const botYamlPath = path.join(botPath, "bot.yaml");
  const current = readYaml<Record<string, unknown>>(botYamlPath);
  if (!current) return;

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { name: _name, ...rest } = updates;
  const merged = { ...current, ...rest };
  writeYaml(botYamlPath, merged);
}

function getBotPath(name: string): string | null {
  const config = getConfig();
  if (!config) return null;
  const botEntry = config.bots.find((b) => b.name === name);
  if (!botEntry) return null;
  return botEntry.path.startsWith("/")
    ? botEntry.path
    : abyssPath(botEntry.path);
}

// --- Tool Metrics (Phase 4) ---

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

// --- Bot Memory ---

export function getBotMemory(name: string): string {
  const botPath = getBotPath(name);
  if (!botPath) return "";
  return readMarkdown(path.join(botPath, "MEMORY.md"));
}

export function updateBotMemory(name: string, content: string): void {
  const botPath = getBotPath(name);
  if (!botPath) return;
  writeMarkdown(path.join(botPath, "MEMORY.md"), content);
}

// --- Cron ---

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

// --- Skills ---

const BUILTIN_SKILL_NAMES = new Set([
  "gcalendar",
  "gmail",
  "image",
  "imessage",
  "jira",
  "qmd",
  "reminders",
  "supabase",
  "translate",
  "twitter",
]);

export function isBuiltinSkill(name: string): boolean {
  return BUILTIN_SKILL_NAMES.has(name);
}

export function listSkills(): SkillConfig[] {
  const skillsDir = abyssPath("skills");
  try {
    const entries = fs.readdirSync(skillsDir, { withFileTypes: true });
    return entries
      .filter((e) => e.isDirectory())
      .map((e) => {
        const skillYaml = readYaml<SkillConfig>(
          path.join(skillsDir, e.name, "skill.yaml"),
        );
        if (!skillYaml) return null;
        return { ...skillYaml, name: skillYaml.name || e.name };
      })
      .filter((s): s is SkillConfig => s !== null);
  } catch {
    return [];
  }
}

export function getSkill(name: string): {
  config: SkillConfig | null;
  skillMarkdown: string;
  mcpConfig: Record<string, unknown> | null;
} {
  const skillDir = abyssPath("skills", name);
  const config = readYaml<SkillConfig>(path.join(skillDir, "skill.yaml"));
  const skillMarkdown = readMarkdown(path.join(skillDir, "SKILL.md"));
  let mcpConfig: Record<string, unknown> | null = null;
  try {
    const mcpContent = fs.readFileSync(
      path.join(skillDir, "mcp.json"),
      "utf-8",
    );
    mcpConfig = JSON.parse(mcpContent);
  } catch {
    // no mcp.json
  }
  return { config, skillMarkdown, mcpConfig };
}

export function createSkill(
  name: string,
  config: Partial<SkillConfig>,
  skillMarkdown: string,
): boolean {
  const skillDir = abyssPath("skills", name);
  if (fs.existsSync(skillDir)) return false;
  fs.mkdirSync(skillDir, { recursive: true });
  const fullConfig: SkillConfig = {
    name,
    type: "cli",
    status: "active",
    description: "",
    allowed_tools: [],
    environment_variables: [],
    environment_variable_values: {},
    required_commands: [],
    install_hints: {},
    ...config,
  };
  writeYaml(path.join(skillDir, "skill.yaml"), fullConfig);
  fs.writeFileSync(path.join(skillDir, "SKILL.md"), skillMarkdown);
  return true;
}

export function updateSkill(
  name: string,
  config: Partial<SkillConfig>,
  skillMarkdown?: string,
): boolean {
  const skillDir = abyssPath("skills", name);
  if (!fs.existsSync(skillDir)) return false;
  const existing = readYaml<SkillConfig>(path.join(skillDir, "skill.yaml"));
  if (!existing) return false;
  writeYaml(path.join(skillDir, "skill.yaml"), { ...existing, ...config });
  if (skillMarkdown !== undefined) {
    fs.writeFileSync(path.join(skillDir, "SKILL.md"), skillMarkdown);
  }
  return true;
}

export function deleteSkill(name: string): boolean {
  const skillDir = abyssPath("skills", name);
  try {
    fs.rmSync(skillDir, { recursive: true, force: true });
    return true;
  } catch {
    return false;
  }
}

// --- Sessions ---

export function getBotSessions(botName: string): SessionInfo[] {
  const botPath = getBotPath(botName);
  if (!botPath) return [];

  const sessionsDir = path.join(botPath, "sessions");
  try {
    const entries = fs.readdirSync(sessionsDir, { withFileTypes: true });
    return entries
      .filter((e) => e.isDirectory() && e.name.startsWith("chat_"))
      .map((e) => {
        const sessionDir = path.join(sessionsDir, e.name);
        const chatId = e.name.replace("chat_", "");

        const conversationFiles: string[] = [];
        let lastActivity: Date | null = null;
        try {
          const files = fs.readdirSync(sessionDir);
          for (const f of files) {
            if (f.startsWith("conversation-") && f.endsWith(".md")) {
              conversationFiles.push(f);
              const stat = fs.statSync(path.join(sessionDir, f));
              if (!lastActivity || stat.mtime > lastActivity) {
                lastActivity = stat.mtime;
              }
            }
          }
        } catch {
          // ignore
        }

        const hasSessionId = fs.existsSync(
          path.join(sessionDir, ".claude_session_id"),
        );

        return {
          chatId,
          lastActivity,
          conversationFiles: conversationFiles.sort(),
          hasSessionId,
        };
      });
  } catch {
    return [];
  }
}

export function deleteSession(botName: string, chatId: string): boolean {
  const botPath = getBotPath(botName);
  if (!botPath) return false;
  const sessionDir = path.join(botPath, "sessions", `chat_${chatId}`);
  try {
    fs.rmSync(sessionDir, { recursive: true, force: true });
    return true;
  } catch {
    return false;
  }
}

export function deleteConversation(
  botName: string,
  chatId: string,
  date: string,
): boolean {
  const botPath = getBotPath(botName);
  if (!botPath) return false;
  if (!/^\d{6}$/.test(date)) return false;
  const filePath = path.join(
    botPath,
    "sessions",
    `chat_${chatId}`,
    `conversation-${date}.md`,
  );
  try {
    fs.unlinkSync(filePath);
    return true;
  } catch {
    return false;
  }
}

export function getConversation(
  botName: string,
  chatId: string,
  date: string,
): string {
  const botPath = getBotPath(botName);
  if (!botPath) return "";
  return readMarkdown(
    path.join(botPath, "sessions", `chat_${chatId}`, `conversation-${date}.md`),
  );
}

// --- Global Memory ---

export function getGlobalMemory(): string {
  return readMarkdown(abyssPath("GLOBAL_MEMORY.md"));
}

export function updateGlobalMemory(content: string): void {
  writeMarkdown(abyssPath("GLOBAL_MEMORY.md"), content);
}

// --- Logs ---

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

function isValidLogFilename(filename: string): boolean {
  return /^abyss-\d{6}\.log$/.test(filename);
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

const DAEMON_LOG_FILES = ["daemon-stdout.log", "daemon-stderr.log"];

export interface DaemonLogInfo {
  name: string;
  size: number;
  exists: boolean;
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

// --- System Status ---

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

// --- Disk Usage ---

export interface DiskUsage {
  totalBytes: number;
  totalFormatted: string;
  breakdown: { name: string; bytes: number; formatted: string }[];
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

// --- Conversation Frequency ---

export interface BotConversationFrequency {
  botName: string;
  displayName: string;
  data: Record<string, number>; // ISO date (YYYY-MM-DD) → user message count
  total: number;
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
      return { botName: bot.name, displayName: bot.display_name || bot.name, data, total: 0 };
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
      displayName: bot.display_name || bot.name,
      data,
      total,
    };
  });
}

// --- Skill Usage ---

export function getSkillUsageByBots(): Record<string, string[]> {
  const bots = listBots();
  const usage: Record<string, string[]> = {};
  for (const bot of bots) {
    for (const skill of bot.skills || []) {
      if (!usage[skill]) usage[skill] = [];
      usage[skill].push(bot.name);
    }
  }
  return usage;
}
