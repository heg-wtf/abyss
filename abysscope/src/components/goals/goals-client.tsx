"use client";

import * as React from "react";

import {
  addGoal,
  deleteGoal,
  fetchGoals,
  listChatBots,
  recordGoalProgress,
  updateGoal,
  type BotSummary,
  type Goal,
} from "@/lib/abyss-api";
import { Button } from "@/components/ui/button";

const STATUS_BADGE: Record<Goal["status"], string> = {
  active: "bg-blue-500/15 text-blue-700 dark:text-blue-300",
  done: "bg-green-500/15 text-green-700 dark:text-green-300",
  archived: "bg-gray-500/15 text-gray-700 dark:text-gray-300",
};

type Filter = "active" | "done" | "archived" | "all";

/**
 * GoalsClient — Phase 6 per-bot goal tracker.
 *
 * Each card shows title / KPI / target / status, a compact timeline
 * of the last 5 progress entries, and inline controls to record
 * progress, mark done, archive, or delete. A second form below adds
 * a new goal. Same shape as SelfClient / ProposalsClient — lazy bot
 * list, inline picker, fetch on bot change.
 */
export function GoalsClient() {
  const [bots, setBots] = React.useState<BotSummary[]>([]);
  const [activeBot, setActiveBot] = React.useState<string | null>(null);
  const [filter, setFilter] = React.useState<Filter>("active");
  const [rows, setRows] = React.useState<Goal[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [newTitle, setNewTitle] = React.useState("");
  const [newKpi, setNewKpi] = React.useState("");
  const [newTarget, setNewTarget] = React.useState("");
  const [progressById, setProgressById] = React.useState<Record<string, string>>(
    {},
  );

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
        const options = filter === "all" ? {} : { status: filter };
        const resp = await fetchGoals(bot, options);
        setRows(resp.goals);
      } catch (caught: unknown) {
        setError(caught instanceof Error ? caught.message : "failed to load goals");
      } finally {
        setLoading(false);
      }
    },
    [filter],
  );

  React.useEffect(() => {
    if (activeBot) void reload(activeBot);
  }, [activeBot, reload]);

  const onAddGoal = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!activeBot || !newTitle.trim()) return;
    setBusyId("__add__");
    setError(null);
    try {
      await addGoal(activeBot, {
        title: newTitle.trim(),
        kpi: newKpi.trim() || undefined,
        target: newTarget.trim() || undefined,
      });
      setNewTitle("");
      setNewKpi("");
      setNewTarget("");
      await reload(activeBot);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "add failed");
    } finally {
      setBusyId(null);
    }
  };

  const onRecordProgress = async (goal: Goal) => {
    if (!activeBot) return;
    const note = (progressById[goal.id] || "").trim();
    if (!note) return;
    setBusyId(goal.id);
    setError(null);
    try {
      await recordGoalProgress(activeBot, goal.id, note);
      setProgressById((current) => ({ ...current, [goal.id]: "" }));
      await reload(activeBot);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "progress failed");
    } finally {
      setBusyId(null);
    }
  };

  const onMark = async (goal: Goal, status: Goal["status"]) => {
    if (!activeBot) return;
    setBusyId(goal.id);
    setError(null);
    try {
      await updateGoal(activeBot, goal.id, { status });
      await reload(activeBot);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "update failed");
    } finally {
      setBusyId(null);
    }
  };

  const onDelete = async (goal: Goal) => {
    if (!activeBot) return;
    if (!window.confirm(`Delete "${goal.title}"? This is irreversible.`)) {
      return;
    }
    setBusyId(goal.id);
    setError(null);
    try {
      await deleteGoal(activeBot, goal.id);
      await reload(activeBot);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "delete failed");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium" htmlFor="goals-bot">
          Bot:
        </label>
        <select
          id="goals-bot"
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
        <label className="text-sm font-medium" htmlFor="goals-filter">
          Status:
        </label>
        <select
          id="goals-filter"
          value={filter}
          onChange={(event) => setFilter(event.target.value as Filter)}
          className="rounded-md border bg-background px-2 py-1 text-sm"
        >
          <option value="active">Active</option>
          <option value="done">Done</option>
          <option value="archived">Archived</option>
          <option value="all">All</option>
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
          No goals — add one below to give this bot something to track.
        </p>
      )}

      <ul className="space-y-3">
        {rows.map((goal) => (
          <li key={goal.id} className="rounded-lg border bg-card p-4 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="font-semibold">
                {goal.title}{" "}
                <span className="text-xs font-mono text-muted-foreground">
                  ({goal.id})
                </span>
              </div>
              <span
                className={`rounded px-2 py-0.5 text-xs ${STATUS_BADGE[goal.status]}`}
              >
                {goal.status}
              </span>
            </div>
            {(goal.kpi || goal.target) && (
              <div className="text-xs text-muted-foreground">
                {goal.kpi && (
                  <span>
                    <strong>KPI:</strong> {goal.kpi}
                  </span>
                )}
                {goal.kpi && goal.target && <span> · </span>}
                {goal.target && (
                  <span>
                    <strong>Target:</strong> {goal.target}
                  </span>
                )}
              </div>
            )}
            {goal.progress.length > 0 && (
              <ul className="ml-4 list-disc text-sm text-muted-foreground">
                {goal.progress.slice(-5).map((entry, index) => (
                  <li key={`${entry.ts}-${index}`}>
                    <span className="font-mono text-xs">{entry.ts}</span>:{" "}
                    {entry.note}
                    {entry.value != null && (
                      <span className="ml-1 text-xs">(+{entry.value})</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {goal.status === "active" && (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void onRecordProgress(goal);
                }}
                className="flex flex-wrap items-center gap-2"
              >
                <input
                  aria-label={`Progress note for ${goal.id}`}
                  placeholder="Add a progress note…"
                  value={progressById[goal.id] || ""}
                  onChange={(event) =>
                    setProgressById((current) => ({
                      ...current,
                      [goal.id]: event.target.value,
                    }))
                  }
                  className="flex-1 min-w-[12rem] rounded-md border bg-background px-2 py-1 text-sm"
                />
                <Button
                  type="submit"
                  size="sm"
                  disabled={busyId === goal.id}
                >
                  Log progress
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void onMark(goal, "done")}
                  disabled={busyId === goal.id}
                >
                  Done
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void onMark(goal, "archived")}
                  disabled={busyId === goal.id}
                >
                  Archive
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => void onDelete(goal)}
                  disabled={busyId === goal.id}
                >
                  Delete
                </Button>
              </form>
            )}
            {goal.status !== "active" && (
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void onMark(goal, "active")}
                  disabled={busyId === goal.id}
                >
                  Reopen
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => void onDelete(goal)}
                  disabled={busyId === goal.id}
                >
                  Delete
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>

      <form
        onSubmit={onAddGoal}
        className="rounded-lg border bg-card p-4 space-y-2"
        aria-label="Add new goal"
      >
        <h2 className="text-sm font-semibold">Add a goal</h2>
        <div className="grid gap-2 sm:grid-cols-3">
          <input
            aria-label="Title"
            placeholder="Title"
            value={newTitle}
            onChange={(event) => setNewTitle(event.target.value)}
            className="rounded-md border bg-background px-2 py-1 text-sm"
          />
          <input
            aria-label="KPI"
            placeholder="KPI (optional)"
            value={newKpi}
            onChange={(event) => setNewKpi(event.target.value)}
            className="rounded-md border bg-background px-2 py-1 text-sm"
          />
          <input
            aria-label="Target"
            placeholder="Target (optional)"
            value={newTarget}
            onChange={(event) => setNewTarget(event.target.value)}
            className="rounded-md border bg-background px-2 py-1 text-sm"
          />
        </div>
        <Button
          type="submit"
          size="sm"
          disabled={busyId === "__add__" || !newTitle.trim()}
        >
          Add goal
        </Button>
      </form>
    </div>
  );
}
