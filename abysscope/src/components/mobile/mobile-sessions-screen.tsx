"use client";

import * as React from "react";
import Link from "next/link";
import { AlertCircle } from "lucide-react";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { BotSummary } from "@/lib/abyss-api";

interface Props {
  apiOnline: boolean;
  bots: BotSummary[];
}

/**
 * Phase 2 placeholder for the mobile session list.
 *
 * The full session list, last-message preview, rename, and long-press
 * action sheet are deferred to Phase 3. This component only proves the
 * data fetch + viewport sizing so we can validate Tailscale access and
 * mobile Safari rendering before iterating on the UI.
 */
export function MobileSessionsScreen({ apiOnline, bots }: Props) {
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 items-center justify-between border-b px-4">
        <h1 className="text-base font-semibold">Abyss</h1>
        <Link
          href="/chat"
          className="text-xs text-muted-foreground underline-offset-2 hover:underline"
        >
          Desktop UI
        </Link>
      </header>

      <main className="flex-1 overflow-y-auto px-4 py-6">
        {!apiOnline && (
          <Alert variant="destructive" className="mb-4">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Chat backend unreachable</AlertTitle>
            <AlertDescription>
              The internal chat server is not responding. Make sure
              <code className="px-1">abyss start</code> is running on your Mac
              and Tailscale (if used) is connected.
            </AlertDescription>
          </Alert>
        )}

        <section className="space-y-2">
          <h2 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Bots ({bots.length})
          </h2>
          {bots.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No bots configured yet.
            </p>
          ) : (
            <ul className="divide-y rounded-lg border">
              {bots.map((bot) => (
                <li key={bot.name} className="flex items-center gap-3 p-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-muted text-sm font-medium">
                    {(bot.display_name || bot.name).slice(0, 1).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">
                      {bot.display_name || bot.name}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {bot.type}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="mt-8 rounded-lg border bg-muted/30 p-4 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">Phase 2 skeleton</p>
          <p className="mt-1 leading-relaxed">
            This is the mobile route stub. Phase 3 will turn the bot list
            above into a session list with last-message previews, custom
            chat names, and a hamburger that opens this screen from the
            chat view. Phase 4 wires up the chat screen itself.
          </p>
        </section>
      </main>

      <footer className="border-t p-4">
        <Button variant="outline" className="w-full" disabled>
          New chat (Phase 3)
        </Button>
      </footer>
    </div>
  );
}
