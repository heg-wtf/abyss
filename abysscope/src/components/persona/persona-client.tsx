"use client";

import * as React from "react";

import {
  fetchPersonaDrift,
  fetchPersonaSnapshots,
  listChatBots,
  triggerPersonaSnapshot,
  type BotSummary,
  type PersonaDriftReport,
  type PersonaSnapshot,
} from "@/lib/abyss-api";
import { Button } from "@/components/ui/button";

const EVENT_BADGE: Record<PersonaSnapshot["event"], string> = {
  daily: "bg-blue-500/15 text-blue-700 dark:text-blue-300",
  "post-compact": "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  manual: "bg-gray-500/15 text-gray-700 dark:text-gray-300",
};

/**
 * PersonaClient — Phase 8.0 drift viewer.
 *
 * Per-bot view of recent snapshots + the latest drift report. The
 * "Take snapshot" button drives the manual REST trigger so a human
 * can grab a baseline without waiting for the daily cron.
 */
export function PersonaClient() {
  const [bots, setBots] = React.useState<BotSummary[]>([]);
  const [activeBot, setActiveBot] = React.useState<string | null>(null);
  const [snapshots, setSnapshots] = React.useState<PersonaSnapshot[]>([]);
  const [drift, setDrift] = React.useState<PersonaDriftReport | null>(null);
  const [windowDays, setWindowDays] = React.useState(7);
  const [loading, setLoading] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
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
      try {
        const [snapResp, driftResp] = await Promise.all([
          fetchPersonaSnapshots(bot, { limit: 30 }),
          fetchPersonaDrift(bot, { window: windowDays }),
        ]);
        setSnapshots(snapResp.snapshots);
        setDrift(driftResp.drift);
      } catch (caught: unknown) {
        setError(
          caught instanceof Error ? caught.message : "failed to load persona data",
        );
      } finally {
        setLoading(false);
      }
    },
    [windowDays],
  );

  React.useEffect(() => {
    if (activeBot) void reload(activeBot);
  }, [activeBot, reload]);

  const onSnapshot = async () => {
    if (!activeBot) return;
    setBusy(true);
    setError(null);
    try {
      await triggerPersonaSnapshot(activeBot);
      await reload(activeBot);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "snapshot failed");
    } finally {
      setBusy(false);
    }
  };

  const sortedSectionDeltas = React.useMemo(() => {
    if (!drift) return [];
    return Object.entries(drift.section_deltas)
      .filter(([, delta]) => delta !== 0)
      .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a))
      .slice(0, 8);
  }, [drift]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium" htmlFor="persona-bot">
          Bot:
        </label>
        <select
          id="persona-bot"
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
        <label className="text-sm font-medium" htmlFor="persona-window">
          Window:
        </label>
        <input
          id="persona-window"
          type="number"
          min="1"
          max="90"
          value={windowDays}
          onChange={(event) =>
            setWindowDays(Math.max(1, Math.min(90, Number(event.target.value) || 7)))
          }
          className="w-20 rounded-md border bg-background px-2 py-1 text-sm"
        />
        <span className="text-xs text-muted-foreground">days</span>
        <Button
          type="button"
          size="sm"
          onClick={() => void onSnapshot()}
          disabled={busy || !activeBot}
        >
          Take snapshot
        </Button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}

      <section className="rounded-lg border bg-card p-4 space-y-2">
        <h2 className="text-sm font-semibold">Drift report</h2>
        {!drift && !loading && (
          <p className="text-sm text-muted-foreground">
            Not enough snapshot history yet — at least two are needed. Take a
            snapshot or schedule the daily cron with{" "}
            <code className="font-mono text-xs">abyss persona schedule {activeBot ?? "<bot>"}</code>
            .
          </p>
        )}
        {drift && (
          <div className="space-y-2 text-sm">
            <div className="flex flex-wrap items-center gap-3">
              <span
                className={`rounded px-2 py-0.5 text-xs ${
                  drift.shrinkage_alert
                    ? "bg-red-500/15 text-red-700 dark:text-red-300"
                    : "bg-green-500/15 text-green-700 dark:text-green-300"
                }`}
              >
                {drift.shrinkage_alert ? "⚠️ Shrinkage alert" : "Stable"}
              </span>
              <span className="text-xs text-muted-foreground">
                {drift.baseline_ts} → {drift.latest_ts}
              </span>
            </div>
            <div>
              Total: {drift.baseline_bytes.toLocaleString()} →{" "}
              {drift.latest_bytes.toLocaleString()} bytes (
              <strong>
                {drift.total_delta_bytes >= 0 ? "+" : ""}
                {drift.total_delta_bytes.toLocaleString()}
              </strong>
              , {(drift.total_delta_pct * 100).toFixed(1)}%)
            </div>
            <div className="text-xs text-muted-foreground">
              Hash {drift.hash_changed ? "changed" : "unchanged"}
            </div>
            {sortedSectionDeltas.length > 0 && (
              <div>
                <div className="text-xs font-semibold mb-1">
                  Section deltas (top {sortedSectionDeltas.length})
                </div>
                <ul className="ml-4 list-disc text-xs text-muted-foreground">
                  {sortedSectionDeltas.map(([name, delta]) => (
                    <li key={name}>
                      {name}: <strong>{delta >= 0 ? "+" : ""}{delta.toLocaleString()}</strong>{" "}
                      bytes
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold">Recent snapshots</h2>
        {snapshots.length === 0 && !loading && (
          <p className="text-sm text-muted-foreground">
            No snapshots yet. Click <em>Take snapshot</em> above to record one
            now.
          </p>
        )}
        {snapshots.length > 0 && (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Timestamp</th>
                  <th className="px-3 py-2">Event</th>
                  <th className="px-3 py-2">Total bytes</th>
                  <th className="px-3 py-2">Sections</th>
                  <th className="px-3 py-2">Hash</th>
                </tr>
              </thead>
              <tbody>
                {snapshots.map((snap) => (
                  <tr
                    key={`${snap.ts}-${snap.hash}`}
                    className="border-t hover:bg-muted/40"
                  >
                    <td className="px-3 py-2 font-mono text-xs">{snap.ts}</td>
                    <td className="px-3 py-2">
                      <span
                        className={`rounded px-2 py-0.5 text-xs ${EVENT_BADGE[snap.event]}`}
                      >
                        {snap.event}
                      </span>
                    </td>
                    <td className="px-3 py-2">{snap.total_bytes.toLocaleString()}</td>
                    <td className="px-3 py-2">
                      {Object.keys(snap.section_sizes).length}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {snap.hash.slice(0, 12)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
