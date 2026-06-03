"use client";

import * as React from "react";

import {
  approveSkillProposal,
  fetchSkillProposals,
  listChatBots,
  rejectSkillProposal,
  type BotSummary,
  type SkillProposal,
} from "@/lib/abyss-api";
import { Button } from "@/components/ui/button";

/**
 * ProposalsClient — Phase 5 skill-autonomy reviewer.
 *
 * Per-bot view of the proposal queue. Approve clicks fire the
 * server-side import + attach + status update; reject just flips
 * status. Failures stream back through the same payload (no exception)
 * so the UI can show a stage + error inline.
 */
type StatusFilter = "pending" | "approved" | "rejected" | "all";

const STATUS_BADGE: Record<SkillProposal["status"], string> = {
  pending: "bg-yellow-500/15 text-yellow-700 dark:text-yellow-300",
  approved: "bg-green-500/15 text-green-700 dark:text-green-300",
  rejected: "bg-red-500/15 text-red-700 dark:text-red-300",
};

export function ProposalsClient() {
  const [bots, setBots] = React.useState<BotSummary[]>([]);
  const [activeBot, setActiveBot] = React.useState<string | null>(null);
  const [statusFilter, setStatusFilter] = React.useState<StatusFilter>("pending");
  const [rows, setRows] = React.useState<SkillProposal[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);

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
        const options =
          statusFilter === "all" ? {} : { status: statusFilter };
        const resp = await fetchSkillProposals(bot, options);
        setRows(resp.proposals);
      } catch (caught: unknown) {
        setError(
          caught instanceof Error ? caught.message : "failed to load proposals",
        );
      } finally {
        setLoading(false);
      }
    },
    [statusFilter],
  );

  React.useEffect(() => {
    if (activeBot) void reload(activeBot);
  }, [activeBot, reload]);

  const onApprove = React.useCallback(
    async (proposal: SkillProposal) => {
      if (!activeBot) return;
      setBusyId(proposal.id);
      setError(null);
      setNotice(null);
      try {
        const result = await approveSkillProposal(activeBot, proposal.id);
        if (!result.ok) {
          // Skip reload on failure so the error message isn't wiped
          // by ``reload``'s setError(null) at the top of its body.
          setError(
            `Approve failed at ${result.stage ?? "?"}: ${result.error ?? "unknown"}`,
          );
        } else {
          setNotice(
            `Installed ${result.skill_name ?? "skill"} and attached to ${activeBot}.`,
          );
          await reload(activeBot);
        }
      } catch (caught: unknown) {
        setError(
          caught instanceof Error ? caught.message : "approve request failed",
        );
      } finally {
        setBusyId(null);
      }
    },
    [activeBot, reload],
  );

  const onReject = React.useCallback(
    async (proposal: SkillProposal) => {
      if (!activeBot) return;
      if (
        !window.confirm(
          `Reject ${proposal.candidate_url}? Bot will not re-propose the same URL.`,
        )
      ) {
        return;
      }
      setBusyId(proposal.id);
      setError(null);
      setNotice(null);
      try {
        await rejectSkillProposal(activeBot, proposal.id);
        await reload(activeBot);
      } catch (caught: unknown) {
        setError(
          caught instanceof Error ? caught.message : "reject request failed",
        );
      } finally {
        setBusyId(null);
      }
    },
    [activeBot, reload],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm font-medium" htmlFor="proposals-bot">
          Bot:
        </label>
        <select
          id="proposals-bot"
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
        <label className="text-sm font-medium" htmlFor="proposals-status">
          Status:
        </label>
        <select
          id="proposals-status"
          value={statusFilter}
          onChange={(event) =>
            setStatusFilter(event.target.value as StatusFilter)
          }
          className="rounded-md border bg-background px-2 py-1 text-sm"
        >
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="all">All</option>
        </select>
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="text-sm text-emerald-600 dark:text-emerald-400">
          {notice}
        </p>
      )}
      {loading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {!loading && rows.length === 0 && !error && (
        <p className="text-sm text-muted-foreground">
          No proposals — the bot will land suggestions here when it notices a
          missing capability.
        </p>
      )}

      <ul className="space-y-3">
        {rows.map((proposal) => (
          <li
            key={proposal.id}
            className="rounded-lg border bg-card p-4 space-y-2"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <a
                href={proposal.candidate_url}
                target="_blank"
                rel="noreferrer"
                className="text-sm font-medium underline-offset-2 hover:underline break-all"
              >
                {proposal.candidate_url}
              </a>
              <span
                className={`rounded px-2 py-0.5 text-xs ${STATUS_BADGE[proposal.status]}`}
              >
                {proposal.status}
              </span>
            </div>
            {proposal.reasons.length > 0 && (
              <ul className="ml-4 list-disc text-sm text-muted-foreground">
                {proposal.reasons.map((reason, index) => (
                  <li key={index}>{reason}</li>
                ))}
              </ul>
            )}
            {proposal.alternative_urls.length > 0 && (
              <div className="text-xs text-muted-foreground">
                <span className="font-semibold">Alternatives:</span>{" "}
                {proposal.alternative_urls.map((url, index) => (
                  <span key={url}>
                    {index > 0 && ", "}
                    <a
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      className="underline-offset-2 hover:underline"
                    >
                      {url}
                    </a>
                  </span>
                ))}
              </div>
            )}
            <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
              <span>Proposed {proposal.proposed_at}</span>
              {proposal.status === "pending" && (
                <div className="flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => void onApprove(proposal)}
                    disabled={busyId === proposal.id}
                  >
                    Approve
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void onReject(proposal)}
                    disabled={busyId === proposal.id}
                  >
                    Reject
                  </Button>
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
