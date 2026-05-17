import path from "path";
import { abyssPath } from "./paths";
import { readYaml, writeYaml } from "./io";
import { getConfig } from "./config";

export interface BotConfig {
  name: string;
  display_name: string;
  /**
   * Optional role / job label. Rendered as
   * ``"<display_name> (<alias>)"`` in list surfaces via
   * ``formatBotLabel``.
   */
  alias?: string | null;
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

export function getBotPath(name: string): string | null {
  const config = getConfig();
  if (!config) return null;
  const botEntry = config.bots.find((b) => b.name === name);
  if (!botEntry) return null;
  return botEntry.path.startsWith("/")
    ? botEntry.path
    : abyssPath(botEntry.path);
}

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
  const botPath = getBotPath(name);
  if (!botPath) return null;
  const botYaml = readYaml<Omit<BotConfig, "name">>(
    path.join(botPath, "bot.yaml"),
  );
  if (!botYaml) return null;
  return { ...botYaml, name } as BotConfig;
}

export function updateBot(name: string, updates: Partial<BotConfig>): void {
  const botPath = getBotPath(name);
  if (!botPath) return;

  const botYamlPath = path.join(botPath, "bot.yaml");
  const current = readYaml<Record<string, unknown>>(botYamlPath);
  if (!current) return;

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { name: _name, ...rest } = updates;
  const merged = { ...current, ...rest } as Record<string, unknown>;
  // ``null`` is the explicit "delete this field" sentinel — used
  // by optional UI fields (e.g. alias) when the user clears them
  // so the YAML stays clean rather than carrying ``alias: null``.
  for (const [key, value] of Object.entries(rest)) {
    if (value === null) {
      delete merged[key];
    }
  }
  writeYaml(botYamlPath, merged);
}
