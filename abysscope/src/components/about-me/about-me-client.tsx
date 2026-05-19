"use client";

import * as React from "react";
import {
  ABOUT_ME_CATEGORIES,
  approveAboutMeEntry,
  fetchAboutMeCategories,
  fetchAboutMeEntries,
  rejectAboutMeEntry,
  updateAboutMeEntry,
  type AboutEntry,
  type AboutEntryStatus,
  type AboutMeCategoriesResponse,
  type AboutMeCategory,
} from "@/lib/abyss-api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

const CATEGORY_LABELS: Record<AboutMeCategory, string> = {
  identity: "Identity",
  relationships: "Relationships",
  preferences: "Preferences",
  routines: "Routines",
  current_focus: "Current Focus",
  health: "Health",
  values: "Values",
};

const STATUS_FILTERS: Array<{ value: "all" | AboutEntryStatus; label: string }> = [
  { value: "all", label: "All" },
  { value: "propose", label: "Pending" },
  { value: "confirmed", label: "Confirmed" },
];

function entryDisplayKey(entry: AboutEntry): string {
  if (entry.conflicts_with) {
    return `${entry.conflicts_with} (conflict)`;
  }
  return entry.key;
}

export function AboutMeClient() {
  const [summary, setSummary] =
    React.useState<AboutMeCategoriesResponse | null>(null);
  const [activeCategory, setActiveCategory] =
    React.useState<AboutMeCategory>("identity");
  const [entries, setEntries] = React.useState<AboutEntry[]>([]);
  const [statusFilter, setStatusFilter] =
    React.useState<"all" | AboutEntryStatus>("all");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const loadSummary = React.useCallback(async () => {
    try {
      const data = await fetchAboutMeCategories();
      setSummary(data);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "unknown error");
    }
  }, []);

  const loadEntries = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await fetchAboutMeEntries(
        activeCategory,
        statusFilter === "all" ? undefined : statusFilter,
      );
      setEntries(list);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "unknown error");
    } finally {
      setLoading(false);
    }
  }, [activeCategory, statusFilter]);

  React.useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  React.useEffect(() => {
    loadEntries();
  }, [loadEntries]);

  const handleApprove = async (entry: AboutEntry) => {
    try {
      await approveAboutMeEntry(activeCategory, entry.key);
      await Promise.all([loadEntries(), loadSummary()]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "approve failed");
    }
  };

  const handleReject = async (entry: AboutEntry) => {
    if (
      !window.confirm(
        `Delete ${entry.key} (${entry.status}) from ${activeCategory}?`,
      )
    ) {
      return;
    }
    try {
      await rejectAboutMeEntry(activeCategory, entry.key);
      await Promise.all([loadEntries(), loadSummary()]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "reject failed");
    }
  };

  const handleUpdate = async (
    entry: AboutEntry,
    patch: { value?: string; body?: string },
  ) => {
    try {
      await updateAboutMeEntry(activeCategory, entry.key, patch);
      await loadEntries();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "update failed");
    }
  };

  const counts = summary?.categories ?? {};
  const pending = summary?.pending_proposals ?? 0;

  return (
    <div className="space-y-6">
      {error ? (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Overview</CardTitle>
          <CardDescription className="text-xs">
            {pending > 0
              ? `${pending} proposal${pending === 1 ? "" : "s"} pending review`
              : "No pending proposals"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            {ABOUT_ME_CATEGORIES.map((category) => {
              const data = counts[category] ?? {
                confirmed: 0,
                propose: 0,
                total: 0,
              };
              const isActive = category === activeCategory;
              return (
                <button
                  key={category}
                  type="button"
                  onClick={() => setActiveCategory(category)}
                  className={`flex flex-col items-start gap-1 rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                    isActive
                      ? "border-primary bg-primary/5"
                      : "border-border bg-background hover:bg-muted"
                  }`}
                >
                  <span className="font-medium">
                    {CATEGORY_LABELS[category]}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {data.confirmed} confirmed
                    {data.propose > 0 ? (
                      <span className="ml-2 inline-flex items-center gap-1">
                        <Badge variant="outline">{data.propose} pending</Badge>
                      </span>
                    ) : null}
                  </span>
                </button>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{CATEGORY_LABELS[activeCategory]}</h2>
        <div className="flex items-center gap-1">
          {STATUS_FILTERS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setStatusFilter(option.value)}
              className={`rounded-md border px-2.5 py-1 text-xs transition-colors ${
                statusFilter === option.value
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-background text-muted-foreground hover:bg-muted"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {statusFilter === "propose"
            ? "No pending proposals."
            : "No entries yet."}
        </p>
      ) : (
        <div className="space-y-3">
          {entries.map((entry) => (
            <EntryCard
              key={entry.key}
              entry={entry}
              category={activeCategory}
              onApprove={handleApprove}
              onReject={handleReject}
              onUpdate={handleUpdate}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function EntryCard({
  entry,
  onApprove,
  onReject,
  onUpdate,
}: {
  entry: AboutEntry;
  category: AboutMeCategory;
  onApprove: (entry: AboutEntry) => Promise<void>;
  onReject: (entry: AboutEntry) => Promise<void>;
  onUpdate: (
    entry: AboutEntry,
    patch: { value?: string; body?: string },
  ) => Promise<void>;
}) {
  const [editing, setEditing] = React.useState(false);
  const [draftValue, setDraftValue] = React.useState(entry.value);
  const [draftBody, setDraftBody] = React.useState(entry.body);

  React.useEffect(() => {
    setDraftValue(entry.value);
    setDraftBody(entry.body);
  }, [entry]);

  const isPropose = entry.status === "propose";
  const isConflict = !!entry.conflicts_with;

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div className="space-y-1">
          <CardTitle className="text-sm font-medium">
            {entryDisplayKey(entry)}
          </CardTitle>
          <CardDescription className="text-xs">
            <span className="inline-flex items-center gap-2">
              <Badge variant={isPropose ? "outline" : "secondary"}>
                {entry.status}
              </Badge>
              {isConflict ? (
                <Badge variant="destructive">conflict</Badge>
              ) : null}
              <span className="text-muted-foreground">
                {entry.confidence} · {entry.source || "manual"}
              </span>
              {entry.added ? (
                <span className="text-muted-foreground">added {entry.added}</span>
              ) : null}
              {entry.last_confirmed ? (
                <span className="text-muted-foreground">
                  confirmed {entry.last_confirmed}
                </span>
              ) : null}
            </span>
          </CardDescription>
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          {isPropose ? (
            <Button
              size="sm"
              onClick={() => onApprove(entry)}
              aria-label={`Approve ${entry.key}`}
            >
              Approve
            </Button>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setEditing((open) => !open)}
            aria-label={`Edit ${entry.key}`}
          >
            {editing ? "Cancel" : "Edit"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onReject(entry)}
            aria-label={`Reject ${entry.key}`}
            className="text-destructive hover:text-destructive"
          >
            Reject
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {!editing ? (
          <>
            <p className="text-sm font-medium">{entry.value}</p>
            {entry.body ? (
              <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                {entry.body}
              </p>
            ) : null}
          </>
        ) : (
          <div className="space-y-2">
            <Input
              value={draftValue}
              onChange={(event) => setDraftValue(event.target.value)}
              aria-label="value"
            />
            <Textarea
              value={draftBody}
              onChange={(event) => setDraftBody(event.target.value)}
              placeholder="Optional longer markdown body"
              rows={3}
              aria-label="body"
            />
            <div className="flex justify-end gap-2">
              <Button
                size="sm"
                onClick={async () => {
                  await onUpdate(entry, {
                    value: draftValue,
                    body: draftBody,
                  });
                  setEditing(false);
                }}
              >
                Save
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
