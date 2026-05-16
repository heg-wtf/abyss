"use client";

import * as React from "react";
import Link from "next/link";
import { Clock, HeartPulse, Settings } from "lucide-react";
import type { RoutineSummary } from "@/lib/abyss-api";

export function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`flex-1 px-4 py-2 text-xs uppercase tracking-wider transition-colors ${
        active
          ? "border-b-2 border-foreground font-bold text-foreground"
          : "font-semibold text-muted-foreground hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

export function RoutineKindIcon({ kind }: { kind: RoutineSummary["kind"] }) {
  const Icon = kind === "cron" ? Clock : HeartPulse;
  return <Icon className="size-3.5 shrink-0 text-muted-foreground" />;
}

/**
 * Pinned bottom strip inside the sessions drawer.
 *
 * Hosts the Web Push toggle and the settings entry point. The settings
 * dialog now owns the theme picker so this footer no longer needs the
 * hydration dance — the dialog component does it internally.
 */
export function DrawerFooter() {
  // ``NEXT_PUBLIC_ABYSS_VERSION`` is injected at build time (see the
  // desktop sidebar for the canonical reference). Fall back to
  // ``dev`` when running outside the packaged wheel so a local
  // checkout doesn't pretend to be a released version.
  const version = process.env.NEXT_PUBLIC_ABYSS_VERSION || "dev";
  const commit = process.env.NEXT_PUBLIC_ABYSS_COMMIT;

  return (
    <div className="flex shrink-0 items-center justify-between gap-2 border-t bg-background/80 px-3 py-2 backdrop-blur">
      <span className="font-mono text-xs text-muted-foreground">
        {version}
        {commit && <span className="ml-1.5 opacity-70">({commit})</span>}
      </span>
      <div className="flex items-center gap-2">
        <Link
          href="/settings"
          aria-label="Settings"
          title="Settings"
          className="flex size-9 items-center justify-center rounded-md border bg-background text-foreground transition-colors hover:bg-muted"
        >
          <Settings className="size-4" aria-hidden />
        </Link>
      </div>
    </div>
  );
}
