"use client";

import * as React from "react";
import { Settings } from "lucide-react";

import { SettingsDialog } from "@/components/settings-dialog";

interface SettingsButtonProps {
  /** Compact mode used by the collapsed desktop sidebar — only the icon. */
  compact?: boolean;
}

/**
 * Sidebar entry point for the settings dialog. Owns the dialog ``open``
 * state so consumers (desktop sidebar, mobile drawer) don't have to wire
 * it up themselves.
 */
export function SettingsButton({ compact = false }: SettingsButtonProps) {
  const [open, setOpen] = React.useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open settings"
        title="Settings"
        className={
          compact
            ? "inline-flex size-9 items-center justify-center rounded-md border bg-background text-foreground transition-colors hover:bg-muted"
            : "inline-flex size-9 items-center justify-center rounded-md border bg-background text-foreground transition-colors hover:bg-muted"
        }
      >
        <Settings className="size-4" aria-hidden />
      </button>
      <SettingsDialog open={open} onOpenChange={setOpen} />
    </>
  );
}
