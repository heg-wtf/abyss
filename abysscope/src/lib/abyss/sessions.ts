import fs from "fs";
import path from "path";
import { readMarkdown } from "./io";
import { getBotPath } from "./bots";

export interface SessionInfo {
  chatId: string;
  lastActivity: Date | null;
  conversationFiles: string[];
  hasSessionId: boolean;
}

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
  if (!fs.existsSync(sessionDir)) return false;
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
