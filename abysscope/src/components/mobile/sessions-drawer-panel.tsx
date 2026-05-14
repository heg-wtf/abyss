"use client";

import * as React from "react";
import { Menu } from "@base-ui/react/menu";
import { MessageSquarePlus, X } from "lucide-react";
import { BotAvatar } from "@/components/bot-avatar";
import { Button } from "@/components/ui/button";
import type { BotSummary, ChatSession } from "@/lib/abyss-api";

interface Props {
  /** Bot id currently shown in the chat behind the drawer. */
  activeBot: string;
  activeSessionId: string;
  onSelect: (target: { bot: string; id: string }) => void;
  onCreate: (botName: string, sessionId: string) => void;
}

/**
 * Compact session list that lives inside the hamburger slide drawer.
 *
 * The main ``MobileSessionsScreen`` is a full-page surface with its
 * own header (bell, "New" menu), bot picker, rename / delete
 * dialogs, etc. Reusing it inside a drawer would duplicate the
 * header and confuse rename state. This panel keeps the contract
 * tight: list bots + their sessions, plus a single "New chat"
 * button that opens the bot picker.
 *
 * Long-press rename / delete actions stay on the full
 * ``/mobile`` sessions page so the drawer remains a fast switcher.
 */
export function SessionsDrawerPanel({
  activeBot,
  activeSessionId,
  onSelect,
  onCreate,
}: Props) {
  const [bots, setBots] = React.useState<BotSummary[]>([]);
  const [sessions, setSessions] = React.useState<ChatSession[]>([]);
  const [loading, setLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const botResp = await fetch("/api/chat/bots");
      const botData = botResp.ok ? await botResp.json() : { bots: [] };
      const botList: BotSummary[] = botData.bots ?? [];
      setBots(botList);

      const all = await Promise.all(
        botList.map(async (bot) => {
          const sessResp = await fetch(
            `/api/chat/sessions?bot=${encodeURIComponent(bot.name)}`,
          );
          if (!sessResp.ok) return [] as ChatSession[];
          const data = (await sessResp.json()) as { sessions: ChatSession[] };
          return data.sessions;
        }),
      );
      const merged = all
        .flat()
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
      setSessions(merged);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const handleCreate = async (botName: string) => {
    try {
      const resp = await fetch("/api/chat/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bot: botName }),
      });
      if (!resp.ok) return;
      const created = (await resp.json()) as ChatSession;
      onCreate(botName, created.id);
    } catch {
      // ignore; the drawer can be reopened
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-14 shrink-0 items-center justify-between border-b px-4">
        <span className="text-base font-semibold">Sessions</span>
        <Menu.Root>
          <Menu.Trigger
            disabled={bots.length === 0}
            render={
              <Button size="sm" variant="default">
                <MessageSquarePlus className="size-4" />
                New
              </Button>
            }
          />
          <Menu.Portal>
            <Menu.Positioner sideOffset={6} align="end">
              <Menu.Popup className="z-50 min-w-[200px] rounded-md border bg-popover p-1 text-sm shadow-md outline-none">
                {bots.map((bot) => (
                  <Menu.Item
                    key={bot.name}
                    onClick={() => handleCreate(bot.name)}
                    className="flex cursor-pointer items-center gap-2 rounded-sm px-2 py-2 outline-none data-highlighted:bg-muted"
                  >
                    <BotAvatar
                      botName={bot.name}
                      displayName={bot.display_name}
                      size="sm"
                    />
                    <span className="truncate">{bot.display_name}</span>
                  </Menu.Item>
                ))}
              </Menu.Popup>
            </Menu.Positioner>
          </Menu.Portal>
        </Menu.Root>
      </header>

      <ul className="flex-1 overflow-y-auto">
        {loading && sessions.length === 0 ? (
          <li className="px-4 py-3 text-sm text-muted-foreground">Loading…</li>
        ) : sessions.length === 0 ? (
          <li className="px-4 py-3 text-sm text-muted-foreground">
            No chats yet. Tap <span className="font-semibold">New</span> above.
          </li>
        ) : (
          sessions.map((sess) => {
            const isActive =
              sess.bot === activeBot && sess.id === activeSessionId;
            const label =
              sess.custom_name?.trim() ||
              sess.bot_display_name ||
              sess.bot;
            return (
              <li key={`${sess.bot}:${sess.id}`}>
                <button
                  type="button"
                  onClick={() => onSelect({ bot: sess.bot, id: sess.id })}
                  className={`flex w-full items-center gap-3 border-b px-4 py-3 text-left active:bg-muted ${
                    isActive ? "bg-muted/60" : ""
                  }`}
                >
                  <BotAvatar
                    botName={sess.bot}
                    displayName={sess.bot_display_name || sess.bot}
                    size="md"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{label}</div>
                    <div className="truncate text-xs text-muted-foreground">
                      {sess.preview || "(no messages yet)"}
                    </div>
                  </div>
                </button>
              </li>
            );
          })
        )}
      </ul>

      <footer className="shrink-0 border-t p-3">
        <a
          href="/mobile"
          className="flex items-center justify-center gap-2 rounded-md border px-3 py-2 text-xs text-muted-foreground hover:bg-muted"
        >
          Manage chats <X className="size-3 rotate-45" />
        </a>
      </footer>
    </div>
  );
}
