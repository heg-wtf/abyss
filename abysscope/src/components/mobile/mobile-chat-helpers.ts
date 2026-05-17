import { formatBotLabel, type ChatSession } from "@/lib/abyss-api";

export function newId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function sessionLabel(session: ChatSession): string {
  // ``custom_name`` (user-assigned) wins. Otherwise compose the bot
  // display name with the optional alias for the chat header. Note
  // that message bubbles intentionally skip the alias — they use the
  // bare ``display_name`` so per-message labels stay terse.
  return (
    session.custom_name?.trim() ||
    formatBotLabel({
      display_name: session.bot_display_name || session.bot,
      alias: session.bot_alias,
    })
  );
}

export function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
