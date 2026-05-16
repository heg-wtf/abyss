import fs from "fs";
import os from "os";
import path from "path";
import yaml from "js-yaml";
import { NextRequest } from "next/server";

export interface TestHomeHandle {
  home: string;
  cleanup: () => void;
}

export function mountTestHome(): TestHomeHandle {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "api-route-"));
  const original = process.env.ABYSS_HOME;
  process.env.ABYSS_HOME = home;
  return {
    home,
    cleanup: () => {
      if (original) process.env.ABYSS_HOME = original;
      else delete process.env.ABYSS_HOME;
      fs.rmSync(home, { recursive: true, force: true });
    },
  };
}

export function writeYamlFile(filePath: string, data: unknown): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, yaml.dump(data), "utf-8");
}

export function writeFile(filePath: string, content: string): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content, "utf-8");
}

export function setupBasicConfig(home: string): void {
  writeYamlFile(path.join(home, "config.yaml"), {
    bots: [{ name: "testbot", path: "bots/testbot" }],
    timezone: "Asia/Seoul",
    language: "Korean",
    settings: { command_timeout: 120, log_level: "INFO" },
  });
  writeYamlFile(path.join(home, "bots", "testbot", "bot.yaml"), {
    telegram_token: "secret-token",
    telegram_username: "test_user",
    telegram_botname: "testbot",
    display_name: "Test Bot",
    personality: "p",
    role: "r",
    goal: "g",
    model: "sonnet",
    streaming: true,
    skills: ["qmd"],
    allowed_users: [],
  });
}

export function makeRequest(
  url: string,
  init?: RequestInit & { json?: unknown },
): NextRequest {
  const finalInit: RequestInit = { ...init };
  if (init?.json !== undefined) {
    finalInit.body = JSON.stringify(init.json);
    finalInit.headers = {
      "Content-Type": "application/json",
      ...(init.headers as Record<string, string> | undefined),
    };
  }
  return new NextRequest(`http://localhost${url}`, finalInit);
}

export function asParams<T>(value: T): Promise<T> {
  return Promise.resolve(value);
}
