"use client";

import * as React from "react";

import {
  fetchEpisodes,
  listChatBots,
  type BotSummary,
  type EpisodeRow,
} from "@/lib/abyss-api";

const KIND_LABEL: Record<EpisodeRow["kind"], string> = {
  fact: "📌 Fact",
  event: "🌀 Event",
  decision: "🧭 Decision",
  change: "🔄 Change",
};

/**
 * EpisodesClient — Phase 4 timeline viewer.
 *
 * Same shape as SelfClient: lazy bot list, inline picker, fetch on
 * bot change. The timeline is read-only — extraction lands rows
 * through the cron, the dashboard surfaces them and groups by date.
 */
export function EpisodesClient() {
  const [bots, setBots] = React.useState<BotSummary[]>([]);
  const [activeBot, setActiveBot] = React.useState<string | null>(null);
  const [rows, setRows] = React.useState<EpisodeRow[]>([]);
  const [kindFilter, setKindFilter] = React.useState<string>("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    listChatBots()
      .then((list) => {
        if (cancelled) return;
        setBots(list);
        if (list.length > 0) {
          setActiveBot((current) => current ?? list[0].name);
        }
      })
      .catch((caught: unknown) =>
        setError(caught instanceof Error ? caught.message : "failed to load bots"),
      );
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    if (!activeBot) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchEpisodes(activeBot, kindFilter ? { kind: kindFilter, limit: 200 } : { limit: 200 })
      .then((resp) => {
        if (!cancelled) setRows(resp.episodes);
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "failed to load episodes");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeBot, kindFilter]);

  // Group rows by date for a tidy timeline rendering.
  const grouped = React.useMemo(() => {
    const out: Record<string, EpisodeRow[]> = {};
    for (const row of rows) {
      (out[row.date] ??= []).push(row);
    }
    return out;
  }, [rows]);
  const dates = Object.keys(grouped).sort((a, b) => (a > b ? -1 : 1));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium" htmlFor="episodes-bot">
          Bot:
        </label>
        <select
          id="episodes-bot"
          value={activeBot ?? ""}
          onChange={(event) => setActiveBot(event.target.value || null)}
          className="rounded-md border bg-background px-2 py-1 text-sm"
        >
          {bots.map((bot) => (
            <option key={bot.name} value={bot.name}>
              {bot.display_name || bot.name}
            </option>
          ))}
        </select>
        <label className="text-sm font-medium" htmlFor="episodes-kind">
          Kind:
        </label>
        <select
          id="episodes-kind"
          value={kindFilter}
          onChange={(event) => setKindFilter(event.target.value)}
          className="rounded-md border bg-background px-2 py-1 text-sm"
        >
          <option value="">All</option>
          <option value="fact">Fact</option>
          <option value="event">Event</option>
          <option value="decision">Decision</option>
          <option value="change">Change</option>
        </select>
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {!loading && rows.length === 0 && !error && (
        <p className="text-sm text-muted-foreground">
          No episodes yet. Schedule extraction with{" "}
          <code className="font-mono text-xs">abyss episodes schedule {activeBot ?? "<bot>"}</code>
          .
        </p>
      )}

      <ol className="space-y-6">
        {dates.map((date) => (
          <li key={date}>
            <h2 className="mb-2 text-sm font-semibold text-muted-foreground">
              {date}
            </h2>
            <ul className="space-y-2">
              {grouped[date].map((row, index) => (
                <li
                  key={`${row.date}-${row.ts}-${index}`}
                  className="rounded-lg border bg-card px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                    <span>{KIND_LABEL[row.kind]}</span>
                    {row.source_turn && (
                      <span className="truncate font-mono">{row.source_turn}</span>
                    )}
                  </div>
                  <p className="mt-1 text-sm">{row.summary}</p>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  );
}
