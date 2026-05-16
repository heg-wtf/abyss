import path from "path";
import { abyssPath } from "./paths";
import { readYaml, writeYaml } from "./io";
import { getConfig } from "./config";

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
  const merged = { ...current, ...rest };
  writeYaml(botYamlPath, merged);
}
