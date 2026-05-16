import path from "path";
import { abyssPath } from "./paths";
import { readMarkdown, writeMarkdown } from "./io";
import { getBotPath } from "./bots";

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

export function getGlobalMemory(): string {
  return readMarkdown(abyssPath("GLOBAL_MEMORY.md"));
}

export function updateGlobalMemory(content: string): void {
  writeMarkdown(abyssPath("GLOBAL_MEMORY.md"), content);
}
