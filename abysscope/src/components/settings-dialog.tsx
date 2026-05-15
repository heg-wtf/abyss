"use client";

import * as React from "react";
import Link from "next/link";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";
import { ArrowRight, Bell, BellOff, Monitor, Moon, Sun } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { useWebPushContext } from "@/components/web-push-provider";

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
          <NotificationsSection />
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

/**
 * Web Push enable / disable section.
 *
 * Was previously a stand-alone bell button (``PushToggle``) pinned to
 * the mobile sessions drawer footer. Folded into Settings on the
 * user's request — the footer is already crowded and notifications
 * are a "set once" toggle that doesn't need a sticky control.
 *
 * Pulls state from the same ``WebPushProvider`` instance the rest of
 * the app uses so visibility tracking + notification-click routing
 * stay coherent.
 */
function NotificationsSection() {
  const push = useWebPushContext();
  const subscribed = push.status === "subscribed";
  const unsupported = push.status === "unsupported";
  const denied = push.status === "permission-denied";

  return (
    <section className="space-y-2">
      <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Notifications
      </Label>

      <div className="flex items-start gap-3 rounded-md border bg-background/40 px-3 py-3">
        <div className="mt-0.5 text-muted-foreground" aria-hidden>
          {subscribed ? (
            <Bell className="size-4" />
          ) : (
            <BellOff className="size-4" />
          )}
        </div>
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-sm font-medium">
            {subscribed ? "푸시 알림이 켜져 있어요" : "푸시 알림이 꺼져 있어요"}
          </p>
          <p className="text-xs text-muted-foreground">
            봇이 응답하거나 cron / heartbeat 가 결과를 내면 폰으로 알림이
            옵니다. 현재 보고 있는 탭에는 발송하지 않아 중복 알림을
            피해요.
          </p>
          <p className="text-xs text-muted-foreground">
            상태:{" "}
            <span className="font-mono text-foreground">{push.status}</span>
          </p>

          {unsupported && (
            <p className="rounded-md bg-destructive/10 px-2 py-1.5 text-xs text-destructive">
              이 브라우저 / 오리진에선 Web Push 가 지원되지 않아요. HTTPS
              로 접속한 iOS Safari 16.4+, Chrome, Edge 에서 켜주세요.
            </p>
          )}

          {denied && (
            <p className="rounded-md bg-destructive/10 px-2 py-1.5 text-xs text-destructive">
              브라우저 / iOS 설정에서 알림이 차단돼 있어요. 사이트
              알림을 다시 허용한 뒤 새로고침 해주세요.
            </p>
          )}

          {push.error && (
            <p className="text-xs text-destructive">{push.error}</p>
          )}

          <p className="pt-1 text-xs text-muted-foreground">
            iOS 는 홈 화면에 추가된 PWA 에서만 푸시가 도착해요.
          </p>
        </div>
        <div className="shrink-0">
          {subscribed ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => push.disable()}
              disabled={push.pending}
            >
              {push.pending ? "Disabling…" : "Disable"}
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={() => push.enable()}
              disabled={push.pending || denied || unsupported}
            >
              {push.pending ? "Enabling…" : "Enable"}
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}
