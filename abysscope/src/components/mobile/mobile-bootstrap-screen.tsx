"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { MessageSquarePlus } from "lucide-react";
import { BotAvatar } from "@/components/bot-avatar";
import { Button } from "@/components/ui/button";
import type { BotSummary } from "@/lib/abyss-api";

interface Props {
  apiOnline: boolean;
  bots: BotSummary[];
}

/**
 * Fallback UI when ``/mobile`` cannot resolve to an existing chat.
 *
 * Three cases:
 *   1. Backend offline — show the error so the user knows it isn't
 *      their phone / network.
 *   2. No bots configured yet — point them at the CLI / desktop UI.
 *   3. Bots exist but no chats yet — render a single-tap "Start a
 *      chat with <bot>" list so the user gets into the chat surface
 *      without bouncing through a separate list screen.
 *
 * Designed as a transient bootstrap surface; once a session exists,
 * ``/mobile`` redirects straight to it and this never renders again.
 */
export function MobileBootstrapScreen({ apiOnline, bots }: Props) {
  const router = useRouter();
  const [creating, setCreating] = React.useState<string | null>(null);

  const startChat = async (botName: string) => {
    if (creating) return;
    setCreating(botName);
    try {
      const resp = await fetch("/api/chat/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bot: botName }),
      });
      if (!resp.ok) {
        setCreating(null);
        return;
      }
      const data = (await resp.json()) as { id: string };
      router.replace(`/mobile/chat/${botName}/${data.id}`);
    } catch {
      setCreating(null);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-xl font-semibold">Abyss</h1>
      {!apiOnline ? (
        <p className="max-w-sm text-sm text-muted-foreground">
          The local API is offline. Run{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
            abyss start
          </code>{" "}
          on the host machine and pull to refresh.
        </p>
      ) : bots.length === 0 ? (
        <p className="max-w-sm text-sm text-muted-foreground">
          No bots yet. Add one with{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
            abyss bot add
          </code>{" "}
          and reload this page.
        </p>
      ) : (
        <>
          <p className="max-w-sm text-sm text-muted-foreground">
            No chats yet. Pick a bot to start your first conversation.
          </p>
          <ul className="w-full max-w-sm divide-y rounded-lg border">
            {bots.map((bot) => (
              <li key={bot.name}>
                <button
                  type="button"
                  disabled={creating !== null}
                  onClick={() => void startChat(bot.name)}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-muted disabled:opacity-50"
                >
                  <BotAvatar
                    botName={bot.name}
                    displayName={bot.display_name}
                    size="md"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">
                      {bot.display_name}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {creating === bot.name
                        ? "Starting…"
                        : "Tap to start a chat"}
                    </div>
                  </div>
                  <MessageSquarePlus className="size-5 text-muted-foreground" />
                </button>
              </li>
            ))}
          </ul>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.refresh()}
            className="text-xs"
          >
            Refresh
          </Button>
        </>
      )}
    </div>
  );
}
