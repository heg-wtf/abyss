"use client";

import * as React from "react";

import {
  fetchFacts,
  listChatBots,
  retractFact,
  type BotSummary,
  type FactRow,
} from "@/lib/abyss-api";
import { Button } from "@/components/ui/button";

/**
 * FactsClient — Phase 4 structured-fact viewer + retract action.
 *
 * The table loads on bot change. ``Retract`` posts to the chat server
 * (the only write surface for facts), then refreshes the table.
 */
export function FactsClient() {
  const [bots, setBots] = React.useState<BotSummary[]>([]);
  const [activeBot, setActiveBot] = React.useState<string | null>(null);
  const [rows, setRows] = React.useState<FactRow[]>([]);
  const [subjectFilter, setSubjectFilter] = React.useState<string>("");
  const [includeRetracted, setIncludeRetracted] = React.useState(false);
  const [minConfidence, setMinConfidence] = React.useState("0");
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

  const reload = React.useCallback(
    async (bot: string) => {
      setLoading(true);
      setError(null);
      const minConfidenceValue = Number.parseFloat(minConfidence);
      try {
        const resp = await fetchFacts(bot, {
          subject: subjectFilter.trim() || undefined,
          minConfidence: Number.isFinite(minConfidenceValue) ? minConfidenceValue : 0,
          includeRetracted,
          limit: 200,
        });
        setRows(resp.facts);
      } catch (caught: unknown) {
        setError(caught instanceof Error ? caught.message : "failed to load facts");
      } finally {
        setLoading(false);
      }
    },
    [subjectFilter, minConfidence, includeRetracted],
  );

  React.useEffect(() => {
    if (activeBot) void reload(activeBot);
  }, [activeBot, reload]);

  const onRetract = React.useCallback(
    async (fact: FactRow) => {
      if (!activeBot) return;
      if (!window.confirm(`Retract fact #${fact.id} (${fact.subject})?`)) {
        return;
      }
      try {
        await retractFact(activeBot, fact.id);
        await reload(activeBot);
      } catch (caught: unknown) {
        setError(caught instanceof Error ? caught.message : "retract failed");
      }
    },
    [activeBot, reload],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium" htmlFor="facts-bot">
          Bot:
        </label>
        <select
          id="facts-bot"
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
        <input
          aria-label="Subject filter"
          placeholder="Filter by subject"
          value={subjectFilter}
          onChange={(event) => setSubjectFilter(event.target.value)}
          className="rounded-md border bg-background px-2 py-1 text-sm"
        />
        <label className="text-sm">Min confidence:</label>
        <input
          aria-label="Minimum confidence"
          type="number"
          step="0.05"
          min="0"
          max="1"
          value={minConfidence}
          onChange={(event) => setMinConfidence(event.target.value)}
          className="w-20 rounded-md border bg-background px-2 py-1 text-sm"
        />
        <label className="flex items-center gap-1 text-sm">
          <input
            type="checkbox"
            checked={includeRetracted}
            onChange={(event) => setIncludeRetracted(event.target.checked)}
          />
          Include retracted
        </label>
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {!loading && rows.length === 0 && !error && (
        <p className="text-sm text-muted-foreground">
          No facts yet. Run{" "}
          <code className="font-mono text-xs">abyss episodes extract {activeBot ?? "<bot>"}</code>
          {" "}or wait for the nightly cron.
        </p>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2">ID</th>
                <th className="px-3 py-2">Subject</th>
                <th className="px-3 py-2">Claim</th>
                <th className="px-3 py-2">Confidence</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2 text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className="border-t hover:bg-muted/40"
                  data-status={row.status}
                >
                  <td className="px-3 py-2 font-mono text-xs">{row.id}</td>
                  <td className="px-3 py-2">{row.subject}</td>
                  <td className="px-3 py-2">{row.claim}</td>
                  <td className="px-3 py-2">{row.confidence.toFixed(2)}</td>
                  <td className="px-3 py-2">{row.status}</td>
                  <td className="px-3 py-2 text-right">
                    {row.status === "active" ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => void onRetract(row)}
                      >
                        Retract
                      </Button>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
