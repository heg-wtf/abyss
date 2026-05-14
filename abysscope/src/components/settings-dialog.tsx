"use client";

import * as React from "react";
import Link from "next/link";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";
import { ArrowRight, Monitor, Moon, Sun } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";

function useHydrated() {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
}

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Quick-settings modal opened from the sidebar gear button.
 *
 * Layout is intentionally section-based so new categories can be appended
 * without restructuring. Today: appearance only. The full configuration
 * surface (timezone, language, memory, paths) lives on ``/settings`` and is
 * one click away via the footer link.
 */
export function SettingsDialog({ open, onOpenChange }: SettingsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Settings</DialogTitle>
          <DialogDescription>
            Quick toggles. Full configuration lives in the settings page.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 pt-2">
          <AppearanceSection />
        </div>

        <div className="mt-4 flex items-center justify-end border-t pt-3">
          <Link
            href="/settings"
            onClick={() => onOpenChange(false)}
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
          >
            More settings
            <ArrowRight className="size-3.5" aria-hidden />
          </Link>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Theme picker with three modes (Light / Dark / System). ``next-themes``
 * needs the hydration guard or the first paint flashes the wrong option
 * because ``theme`` is undefined on the server.
 */
function AppearanceSection() {
  const { theme, setTheme } = useTheme();
  const mounted = useHydrated();
  const current = mounted ? theme ?? "system" : "system";

  return (
    <section className="space-y-2">
      <Label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Appearance
      </Label>
      <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-2">
        <ThemeOption
          value="light"
          label="Light"
          icon={<Sun className="size-4" aria-hidden />}
          selected={current === "light"}
          onSelect={() => setTheme("light")}
        />
        <ThemeOption
          value="dark"
          label="Dark"
          icon={<Moon className="size-4" aria-hidden />}
          selected={current === "dark"}
          onSelect={() => setTheme("dark")}
        />
        <ThemeOption
          value="system"
          label="System"
          icon={<Monitor className="size-4" aria-hidden />}
          selected={current === "system"}
          onSelect={() => setTheme("system")}
        />
      </div>
    </section>
  );
}

interface ThemeOptionProps {
  value: string;
  label: string;
  icon: React.ReactNode;
  selected: boolean;
  onSelect: () => void;
}

function ThemeOption({ value, label, icon, selected, onSelect }: ThemeOptionProps) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      data-value={value}
      onClick={onSelect}
      className={`flex flex-col items-center gap-1.5 rounded-lg border px-3 py-3 text-xs font-medium transition-colors ${
        selected
          ? "border-primary bg-primary/10 text-foreground"
          : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground"
      }`}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}
