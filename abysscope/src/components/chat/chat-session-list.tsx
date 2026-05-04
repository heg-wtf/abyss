"use client";

import * as React from "react";
import { Menu } from "@base-ui/react/menu";
import { MessageSquarePlus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { BotAvatar } from "@/components/bot-avatar";
import { cn } from "@/lib/utils";
import type { BotSummary, ChatSession } from "@/lib/abyss-api";

interface Props {
  sessions: ChatSession[];
  bots: BotSummary[];
  activeId: string | null;
  onSelect: (session: ChatSession) => void;
  onCreate: (botName: string) => void;
  onDelete: (session: ChatSession) => void;
  loading?: boolean;
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const diff = (Date.now() - then) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

export function ChatSessionList({
  sessions,
  bots,
  activeId,
  onSelect,
  onCreate,
  onDelete,
  loading,
}: Props) {
  const noBots = bots.length === 0;
  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r bg-muted/40">
      <div className="flex h-14 items-center justify-between border-b px-3">
        <span className="text-sm font-medium">Chats</span>
        <Menu.Root>
          <Menu.Trigger
            render={
              <Button size="sm" variant="outline" disabled={noBots}>
                <MessageSquarePlus className="size-4" />
                New
              </Button>
            }
          />
          <Menu.Portal>
            <Menu.Positioner sideOffset={6} align="end">
              <Menu.Popup className="min-w-[200px] rounded-md border bg-popover p-1 text-sm shadow-md outline-none">
                {bots.map((bot) => (
                  <Menu.Item
                    key={bot.name}
                    onClick={() => onCreate(bot.name)}
                    className="flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 outline-none data-highlighted:bg-muted"
                  >
                    <BotAvatar
                      botName={bot.name}
                      displayName={bot.display_name}
                      size="xs"
                    />
                    <span className="truncate">{bot.display_name}</span>
                  </Menu.Item>
                ))}
              </Menu.Popup>
            </Menu.Positioner>
          </Menu.Portal>
        </Menu.Root>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        {loading && (
          <div className="px-3 py-4 text-sm text-muted-foreground">Loading…</div>
        )}
        {!loading && sessions.length === 0 && (
          <div className="px-3 py-4 text-sm text-muted-foreground">
            No chats yet. Click <em>New</em> to start one.
          </div>
        )}
        <ul className="space-y-0.5 p-1">
          {sessions.map((session) => (
            <li key={session.id}>
              <button
                type="button"
                onClick={() => onSelect(session)}
                className={cn(
                  "group flex w-full items-start gap-2 rounded-md px-2 py-2 text-left transition-colors hover:bg-muted",
                  activeId === session.id && "bg-muted"
                )}
              >
                <BotAvatar
                  botName={session.bot}
                  displayName={session.bot_display_name || session.bot}
                  size="sm"
                  className="mt-0.5"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium">
                      {session.bot_display_name || session.bot}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {formatRelative(session.updated_at)}
                    </span>
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    {session.preview || "(empty)"}
                  </div>
                </div>
                <span
                  role="button"
                  tabIndex={0}
                  className="invisible rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive group-hover:visible"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(session);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      e.stopPropagation();
                      onDelete(session);
                    }
                  }}
                >
                  <Trash2 className="size-3.5" />
                </span>
              </button>
            </li>
          ))}
        </ul>
      </ScrollArea>
    </aside>
  );
}
