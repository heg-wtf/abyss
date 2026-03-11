import fs from "fs";
import path from "path";
import yaml from "js-yaml";

const CCLAW_HOME =
  process.env.CCLAW_HOME || path.join(process.env.HOME || "~", ".cclaw");

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
  schedule: string;
  message: string;
  timezone?: string;
  model?: string;
  skills?: string[];
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

function cclawPath(...segments: string[]): string {
  return path.join(CCLAW_HOME, ...segments);
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
  return readYaml<GlobalConfig>(cclawPath("config.yaml"));
}

export function updateConfig(config: GlobalConfig): void {
  writeYaml(cclawPath("config.yaml"), config);
}

// --- Bots ---

export function listBots(): BotConfig[] {
  const config = getConfig();
  if (!config) return [];

  return config.bots
    .map((botEntry) => {
      const botPath = botEntry.path.startsWith("/")
        ? botEntry.path
        : cclawPath(botEntry.path);
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
    : cclawPath(botEntry.path);
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
    : cclawPath(botEntry.path);
  const botYamlPath = path.join(botPath, "bot.yaml");
  const current = readYaml<Record<string, unknown>>(botYamlPath);
  if (!current) return;

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
    : cclawPath(botEntry.path);
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
  "best-price",
  "daiso",
  "dart",
  "gcalendar",
  "gmail",
  "image",
  "imessage",
  "jira",
  "kakao-local",
  "naver-map",
  "naver-search",
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
  const skillsDir = cclawPath("skills");
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
  const skillDir = cclawPath("skills", name);
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
  return readMarkdown(cclawPath("GLOBAL_MEMORY.md"));
}

export function updateGlobalMemory(content: string): void {
  writeMarkdown(cclawPath("GLOBAL_MEMORY.md"), content);
}

// --- Logs ---

export function listLogFiles(): string[] {
  const logsDir = cclawPath("logs");
  try {
    return fs
      .readdirSync(logsDir)
      .filter((f) => f.startsWith("cclaw-") && f.endsWith(".log"))
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
  const logPath = cclawPath("logs", filename);
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

// --- System Status ---

export function getSystemStatus(): SystemStatus {
  const pidPath = cclawPath("cclaw.pid");
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
