"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface SearchHit {
  ts: string;
  role: string;
  chatId: string;
  dateKey: string;
  snippet: string;
}

interface SearchStatus {
  available: boolean;
  fts5Available: boolean;
  dbPath: string;
  dbExists: boolean;
  dbSize: number;
  messageCount: number;
  oldestTs: string | null;
  newestTs: string | null;
}

interface SearchPanelProps {
  botName: string;
}

function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function formatTs(ts: string | null): string {
  if (!ts) return "-";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function renderSnippet(snippet: string) {
  const parts = snippet.split(/(<<.*?>>)/g);
  return parts.map((part, idx) => {
    if (part.startsWith("<<") && part.endsWith(">>")) {
      return (
        <mark
          key={idx}
          className="bg-yellow-300/30 text-foreground rounded px-0.5"
        >
          {part.slice(2, -2)}
        </mark>
      );
    }
    return <span key={idx}>{part}</span>;
  });
}

export function SearchPanel({ botName }: SearchPanelProps) {
  const [status, setStatus] = useState<SearchStatus | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [reindexing, setReindexing] = useState(false);
  const [reindexMsg, setReindexMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lastQueryRef = useRef<string>("");

  const refreshStatus = useCallback(async () => {
    const res = await fetch(`/api/bots/${botName}/search/status`);
    if (res.ok) {
      setStatus(await res.json());
    }
  }, [botName]);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  const runSearch = useCallback(async () => {
    const q = query.trim();
    if (!q) {
      setHits([]);
      lastQueryRef.current = "";
      return;
    }
    setLoading(true);
    setError(null);
    lastQueryRef.current = q;
    try {
      const res = await fetch(
        `/api/bots/${botName}/search?q=${encodeURIComponent(q)}&limit=50`,
      );
      const data = await res.json();
      if (!res.ok) {
        setError(data?.error ?? `Search failed (${res.status})`);
        setHits([]);
      } else {
        setHits(data.hits ?? []);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setHits([]);
    } finally {
      setLoading(false);
    }
  }, [botName, query]);

  const reindex = useCallback(async () => {
    setReindexing(true);
    setReindexMsg(null);
    try {
      const res = await fetch(`/api/bots/${botName}/search/reindex`, {
        method: "POST",
      });
      const data = await res.json();
      if (res.ok) {
        setReindexMsg(`Indexed ${data.count ?? 0} messages.`);
      } else {
        setReindexMsg(`Reindex failed: ${data.error ?? "unknown error"}`);
      }
      await refreshStatus();
      if (lastQueryRef.current) {
        await runSearch();
      }
    } catch (err) {
      setReindexMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setReindexing(false);
    }
  }, [botName, refreshStatus, runSearch]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div>
            <CardTitle className="text-sm">SQLite FTS5 Index</CardTitle>
            <CardDescription>
              Full-text search across this bot&apos;s conversation logs.
            </CardDescription>
          </div>
          <div className="flex flex-col items-end gap-1">
            <Button
              variant="outline"
              size="sm"
              onClick={reindex}
              disabled={reindexing || !status?.fts5Available}
            >
              {reindexing ? "Reindexing…" : "Reindex"}
            </Button>
            {reindexMsg && (
              <span className="text-xs text-muted-foreground">{reindexMsg}</span>
            )}
          </div>
        </CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <Stat label="Messages" value={status?.messageCount?.toLocaleString() ?? "-"} />
          <Stat label="DB size" value={status ? formatBytes(status.dbSize) : "-"} />
          <Stat label="Oldest" value={formatTs(status?.oldestTs ?? null)} />
          <Stat label="Newest" value={formatTs(status?.newestTs ?? null)} />
          <Stat
            label="FTS5"
            value={status?.fts5Available ? "Available" : "Unavailable"}
          />
          <Stat
            label="DB file"
            value={status?.dbExists ? "Exists" : "Missing"}
          />
          <div className="col-span-2 md:col-span-2 text-xs text-muted-foreground break-all">
            {status?.dbPath || "-"}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Search</CardTitle>
          <CardDescription>
            Quote phrases, e.g. <code>release notes</code>. Indexed by
            unicode61 tokenizer.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void runSearch();
            }}
            className="flex gap-2"
          >
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search conversations…"
              autoFocus
            />
            <Button type="submit" disabled={loading || !query.trim()}>
              {loading ? "Searching…" : "Search"}
            </Button>
          </form>

          {error && (
            <div className="text-sm text-red-500">Error: {error}</div>
          )}

          {!loading && lastQueryRef.current && hits.length === 0 && !error && (
            <div className="text-sm text-muted-foreground">
              No matches for &quot;{lastQueryRef.current}&quot;.
            </div>
          )}

          {hits.length > 0 && (
            <div className="text-xs text-muted-foreground">
              {hits.length} result{hits.length === 1 ? "" : "s"}
            </div>
          )}

          <ul className="space-y-2">
            {hits.map((hit, idx) => {
              const chatLabel = hit.chatId
                ? hit.chatId.replace(/^chat_/, "")
                : "";
              const href = chatLabel
                ? `/bots/${botName}/conversations/${chatLabel}?date=${hit.dateKey}`
                : null;
              const headline = (
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span>{formatTs(hit.ts)}</span>
                  <span>·</span>
                  <span>{hit.role || "?"}</span>
                  {chatLabel && (
                    <>
                      <span>·</span>
                      <span className="font-mono">{chatLabel}</span>
                    </>
                  )}
                  {hit.dateKey && (
                    <>
                      <span>·</span>
                      <span>{hit.dateKey}</span>
                    </>
                  )}
                </div>
              );
              return (
                <li
                  key={`${hit.ts}-${idx}`}
                  className="border rounded-md p-3 hover:bg-muted/40"
                >
                  {href ? (
                    <Link href={href} className="block space-y-1">
                      {headline}
                      <p className="text-sm whitespace-pre-wrap">
                        {renderSnippet(hit.snippet)}
                      </p>
                    </Link>
                  ) : (
                    <div className="space-y-1">
                      {headline}
                      <p className="text-sm whitespace-pre-wrap">
                        {renderSnippet(hit.snippet)}
                      </p>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-0.5">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  );
}
