import type { ChatSession } from "@/lib/abyss-api";

export function newId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function sessionLabel(session: ChatSession): string {
  return (
    session.custom_name?.trim() ||
    session.bot_display_name ||
    session.bot
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
