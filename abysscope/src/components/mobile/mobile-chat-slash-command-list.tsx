"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import type { SlashCommandSpec } from "@/lib/abyss-api";

export function SlashCommandList({
  commands,
  onPick,
  onClose,
}: {
  commands: SlashCommandSpec[] | null;
  onPick: (spec: SlashCommandSpec) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = React.useState("");
  const filtered = React.useMemo(() => {
    if (!commands) return [];
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter(
      (cmd) =>
        cmd.name.toLowerCase().includes(needle) ||
        cmd.description.toLowerCase().includes(needle)
    );
  }, [commands, query]);

  if (commands === null) {
    return (
      <p className="px-1 py-4 text-sm text-muted-foreground">Loading…</p>
    );
  }

  if (commands.length === 0) {
    return (
      <p className="px-1 py-4 text-sm text-muted-foreground">
        No commands available.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <input
        type="text"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search commands…"
        className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
        autoFocus
      />
      <ul className="max-h-[50vh] overflow-y-auto divide-y rounded-md border">
        {filtered.map((cmd) => (
          <li key={cmd.name}>
            <button
              type="button"
              className="w-full px-3 py-2 text-left hover:bg-muted"
              onClick={() => onPick(cmd)}
            >
              <div className="font-mono text-sm">/{cmd.name}</div>
              <div className="text-xs text-muted-foreground">
                {cmd.description}
              </div>
              {cmd.usage && (
                <div className="font-mono text-[11px] text-muted-foreground">
                  {cmd.usage}
                </div>
              )}
            </button>
          </li>
        ))}
      </ul>
      <Button variant="ghost" onClick={onClose}>
        Close
      </Button>
    </div>
  );
}
