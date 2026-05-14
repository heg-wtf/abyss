"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import {
  Clock,
  HeartPulse,
  MessageSquarePlus,
  Moon,
  MoreVertical,
  Pencil,
  Sun,
  Trash2,
} from "lucide-react";
import { PushToggle } from "@/components/mobile/push-toggle";
import { BotAvatar } from "@/components/bot-avatar";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type {
  BotSummary,
  ChatSession,
  RoutineSummary,
} from "@/lib/abyss-api";

interface Props {
  /** Bot id currently shown in the chat behind the drawer. */
  activeBot: string;
  activeSessionId: string;
  onSelect: (target: { bot: string; id: string }) => void;
  onCreate: (botName: string, sessionId: string) => void;
}

/**
 * Session list that lives inside the hamburger slide drawer.
 *
 * The drawer is now the only session switcher — the earlier
 * full-page ``MobileSessionsScreen`` was deleted because it
 * duplicated this surface and forced an extra hop on every cold
 * load. This panel owns: tabs (Chats / Routines), inline bot picker
 * for new chats, per-row rename + delete via the ⋮ menu, and the
 * pinned footer that hosts the push + dark-mode toggles.
 */
export function SessionsDrawerPanel({
  activeBot,
  activeSessionId,
  onSelect,
  onCreate,
}: Props) {
  const router = useRouter();
  const [bots, setBots] = React.useState<BotSummary[]>([]);
  const [sessions, setSessions] = React.useState<ChatSession[]>([]);
  const [routines, setRoutines] = React.useState<RoutineSummary[]>([]);
  const [routinesLoading, setRoutinesLoading] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [pickerOpen, setPickerOpen] = React.useState(false);
  const [tab, setTab] = React.useState<"chats" | "routines">("chats");
  const [menuAnchor, setMenuAnchor] = React.useState<{
    session: ChatSession;
    rect: { top: number; left: number; bottom: number; right: number };
  } | null>(null);
  const [renameTarget, setRenameTarget] = React.useState<ChatSession | null>(
    null,
  );
  const [deleteTarget, setDeleteTarget] = React.useState<ChatSession | null>(
    null,
  );

  const openMenuFromEvent = React.useCallback(
    (sess: ChatSession, target: EventTarget | null) => {
      const element = target instanceof HTMLElement ? target : null;
      const rect = element?.getBoundingClientRect();
      if (!rect) return;
      setMenuAnchor({
        session: sess,
        rect: {
          top: rect.top,
          left: rect.left,
          bottom: rect.bottom,
          right: rect.right,
        },
      });
    },
    [],
  );

  React.useEffect(() => {
    if (!menuAnchor) return;
    const close = () => setMenuAnchor(null);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [menuAnchor]);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const botResp = await fetch("/api/chat/bots");
      const botData = botResp.ok ? await botResp.json() : { bots: [] };
      const botList: BotSummary[] = botData.bots ?? [];
      setBots(botList);

      const all = await Promise.all(
        botList.map(async (bot) => {
          const sessResp = await fetch(
            `/api/chat/sessions?bot=${encodeURIComponent(bot.name)}`,
          );
          if (!sessResp.ok) return [] as ChatSession[];
          const data = (await sessResp.json()) as { sessions: ChatSession[] };
          return data.sessions;
        }),
      );
      const merged = all
        .flat()
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
      setSessions(merged);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  // Routines (cron + heartbeat) fetch lazily — only when the tab is
  // opened — so cold-loading the drawer for normal chat use doesn't
  // do an extra network round-trip on phones over Tailscale.
  React.useEffect(() => {
    if (tab !== "routines") return;
    let cancelled = false;
    const run = async () => {
      setRoutinesLoading(true);
      try {
        const response = await fetch("/api/chat/routines");
        if (!response.ok) return;
        const body = (await response.json()) as { routines: RoutineSummary[] };
        if (!cancelled) setRoutines(body.routines ?? []);
      } finally {
        if (!cancelled) setRoutinesLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [tab]);

  const handleCreate = async (botName: string) => {
    try {
      const resp = await fetch("/api/chat/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bot: botName }),
      });
      if (!resp.ok) return;
      const created = (await resp.json()) as ChatSession;
      onCreate(botName, created.id);
    } catch {
      // ignore; the drawer can be reopened
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Tabs sit at the very top of the drawer — the dedicated
          ``Sessions`` header is gone. ``+ New chat`` lives as the
          first list row (Anthropic / Claude.ai mobile pattern)
          instead of a separate header button, which gives the list
          a single column of consistent touch targets.

          ``h-14`` matches the workspace drawer header so the two
          drawers feel symmetric when the user swings between them
          — without this the chats tab bar sat ~23px shorter than
          the workspace header and the chat surface visibly hopped
          up and down behind the drawer. */}
      <div className="flex h-14 shrink-0 border-b bg-muted/20">
        <TabButton
          active={tab === "chats"}
          onClick={() => setTab("chats")}
        >
          Chats
        </TabButton>
        <TabButton
          active={tab === "routines"}
          onClick={() => {
            setTab("routines");
            setPickerOpen(false);
          }}
        >
          Routines
        </TabButton>
      </div>

      {/* Inline bot picker. base-ui ``Menu.Portal`` renders into
          ``document.body``; combined with the drawer's
          ``transform`` containing block that broke the popup's
          positioning and made the "New" tap appear to do nothing.
          Rendering the picker inside the drawer sidesteps the
          portal entirely. */}
      {tab === "chats" && pickerOpen && bots.length > 0 && (
        <ul className="shrink-0 divide-y border-b bg-muted/30">
          {bots.map((bot) => (
            <li key={bot.name}>
              <button
                type="button"
                onClick={() => {
                  setPickerOpen(false);
                  void handleCreate(bot.name);
                }}
                className="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-muted"
              >
                <BotAvatar
                  botName={bot.name}
                  displayName={bot.display_name}
                  size="sm"
                />
                <span className="truncate text-sm">{bot.display_name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <ul className="min-h-0 flex-1 overflow-y-auto">
        {tab === "chats" && (
          <li>
            <button
              type="button"
              disabled={bots.length === 0}
              onClick={() => setPickerOpen((v) => !v)}
              aria-expanded={pickerOpen}
              className="flex w-full items-center gap-3 border-b px-4 py-3 text-left text-sm font-medium active:bg-muted disabled:opacity-50"
            >
              <MessageSquarePlus className="size-5 text-muted-foreground" />
              <span>New chat</span>
            </button>
          </li>
        )}
        {tab === "routines" ? (
          routinesLoading && routines.length === 0 ? (
            <li className="px-4 py-3 text-sm text-muted-foreground">Loading…</li>
          ) : routines.length === 0 ? (
            <li className="px-4 py-6 text-center text-sm text-muted-foreground">
              No routines yet
            </li>
          ) : (
            routines.map((routine) => (
              <li key={`${routine.bot}:${routine.kind}:${routine.job_name}`}>
                <button
                  type="button"
                  onClick={() => {
                    router.push(
                      `/mobile/routine/${routine.bot}/${routine.kind}/${routine.job_name}`,
                    );
                  }}
                  className="flex w-full min-w-0 items-center gap-3 border-b px-4 py-3 text-left active:bg-muted"
                >
                  <BotAvatar
                    botName={routine.bot}
                    displayName={routine.bot_display_name}
                    size="md"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-sm font-medium">
                      <RoutineKindIcon kind={routine.kind} />
                      <span className="truncate">{routine.job_name}</span>
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {routine.preview || "(no runs yet)"}
                    </div>
                  </div>
                </button>
              </li>
            ))
          )
        ) : loading && sessions.length === 0 ? (
          <li className="px-4 py-3 text-sm text-muted-foreground">Loading…</li>
        ) : sessions.length === 0 ? (
          <li className="px-4 py-3 text-sm text-muted-foreground">
            Tap <span className="font-semibold">New chat</span> to start one.
          </li>
        ) : (
          sessions.map((sess) => {
            const key = `${sess.bot}:${sess.id}`;
            const isActive =
              sess.bot === activeBot && sess.id === activeSessionId;
            const label =
              sess.custom_name?.trim() ||
              sess.bot_display_name ||
              sess.bot;
            const menuOpen = menuAnchor?.session.id === sess.id;
            return (
              <li key={key}>
                <div
                  className={`flex min-w-0 items-center border-b ${
                    isActive ? "bg-muted/60" : ""
                  }`}
                  onContextMenu={(event) => {
                    // Desktop / Safari right-click also opens the
                    // per-row actions. The drawer is now the only
                    // place rename / delete live (the "Manage chats"
                    // footer is gone), so the right-click affordance
                    // matters for non-touch testing.
                    event.preventDefault();
                    openMenuFromEvent(sess, event.currentTarget);
                  }}
                >
                  <button
                    type="button"
                    onClick={() => {
                      setMenuAnchor(null);
                      onSelect({ bot: sess.bot, id: sess.id });
                    }}
                    className="flex min-w-0 flex-1 items-center gap-3 px-4 py-3 text-left active:bg-muted"
                  >
                    <BotAvatar
                      botName={sess.bot}
                      displayName={sess.bot_display_name || sess.bot}
                      size="md"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{label}</div>
                      <div className="truncate text-xs text-muted-foreground">
                        {sess.preview || "(no messages yet)"}
                      </div>
                    </div>
                  </button>
                  <button
                    type="button"
                    aria-label="Session actions"
                    aria-expanded={menuOpen}
                    onClick={(event) =>
                      menuOpen
                        ? setMenuAnchor(null)
                        : openMenuFromEvent(sess, event.currentTarget)
                    }
                    className="shrink-0 rounded-md px-2 py-3 text-muted-foreground hover:bg-muted"
                  >
                    <MoreVertical className="size-4" />
                  </button>
                </div>
              </li>
            );
          })
        )}
      </ul>

      {/* Pinned footer — sits at the bottom of the drawer regardless
          of list scroll position. Today this hosts the dark-mode
          toggle (moved here from a global floating action so it
          stops covering chat content); future global drawer
          settings land in the same strip. */}
      <DrawerFooter />

      {/* Action menu — rendered at viewport coordinates via portal
          so the scrollable session list does not clip it. Closes on
          window scroll / resize so a stale popover never floats
          orphaned over the chat behind. */}
      {menuAnchor && (
        <SessionActionsPopover
          anchor={menuAnchor.rect}
          onClose={() => setMenuAnchor(null)}
          onRename={() => {
            setRenameTarget(menuAnchor.session);
            setMenuAnchor(null);
          }}
          onDelete={() => {
            setDeleteTarget(menuAnchor.session);
            setMenuAnchor(null);
          }}
        />
      )}

      <RenameSessionDialog
        session={renameTarget}
        onClose={() => setRenameTarget(null)}
        onRenamed={(updated) =>
          setSessions((prev) =>
            prev.map((s) =>
              s.bot === updated.bot && s.id === updated.id
                ? { ...s, custom_name: updated.custom_name }
                : s,
            ),
          )
        }
      />
      <DeleteSessionDialog
        session={deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onDeleted={(deleted) =>
          setSessions((prev) =>
            prev.filter(
              (s) => !(s.bot === deleted.bot && s.id === deleted.id),
            ),
          )
        }
      />
    </div>
  );
}

function TabButton({
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

function RoutineKindIcon({ kind }: { kind: RoutineSummary["kind"] }) {
  const Icon = kind === "cron" ? Clock : HeartPulse;
  return <Icon className="size-3.5 shrink-0 text-muted-foreground" />;
}

function useHydrated() {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
}

/**
 * Pinned bottom strip inside the sessions drawer.
 *
 * Hosts the dark-mode toggle. ``next-themes`` only knows the resolved
 * theme after hydration, so the body skips SSR via ``useHydrated``
 * to avoid a one-frame icon flicker.
 */
function DrawerFooter() {
  const { theme, setTheme } = useTheme();
  const mounted = useHydrated();
  const isDark = theme === "dark";

  return (
    <div className="flex shrink-0 items-center justify-end gap-2 border-t bg-background/80 px-3 py-2 backdrop-blur">
      <PushToggle />
      {mounted ? (
        <button
          type="button"
          aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
          onClick={() => setTheme(isDark ? "light" : "dark")}
          className="flex size-9 items-center justify-center rounded-md border bg-background text-foreground transition-colors hover:bg-muted"
        >
          {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </button>
      ) : (
        <div className="size-9" aria-hidden />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Per-row context menu actions
// ---------------------------------------------------------------------------

/**
 * Portal-rendered actions menu for a session row.
 *
 * Earlier revisions positioned the menu absolutely inside the row's
 * ``<li>`` element. That works fine for top-of-list rows, but the
 * surrounding ``<ul className="overflow-y-auto">`` clipped the popup
 * for any row near the bottom of the scroll container — the user
 * reported "우클릭 되는데 하단은 안나옴".
 *
 * Rendering through ``createPortal`` to ``document.body`` escapes the
 * scroll container, and positioning via ``getBoundingClientRect``
 * keeps the menu visually anchored to the trigger button. We flip
 * above the anchor when there isn't enough room below so the menu
 * never falls off the viewport edge on short phones.
 */
function SessionActionsPopover({
  anchor,
  onClose,
  onRename,
  onDelete,
}: {
  anchor: { top: number; left: number; bottom: number; right: number };
  onClose: () => void;
  onRename: () => void;
  onDelete: () => void;
}) {
  const [mounted, setMounted] = React.useState(false);
  const menuRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  React.useEffect(() => {
    const onPointer = (event: MouseEvent | TouchEvent) => {
      if (!menuRef.current) return;
      if (menuRef.current.contains(event.target as Node)) return;
      onClose();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("touchstart", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("touchstart", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  if (!mounted) return null;

  const MENU_WIDTH = 176;
  const MENU_HEIGHT = 96;
  const GAP = 6;

  const viewportWidth =
    typeof window === "undefined" ? 360 : window.innerWidth;
  const viewportHeight =
    typeof window === "undefined" ? 640 : window.innerHeight;

  // Flip above the anchor when there isn't enough room below.
  const placeBelow = anchor.bottom + GAP + MENU_HEIGHT <= viewportHeight;
  const top = placeBelow
    ? Math.min(anchor.bottom + GAP, viewportHeight - MENU_HEIGHT - 8)
    : Math.max(anchor.top - GAP - MENU_HEIGHT, 8);
  // Align the menu's right edge with the trigger's right edge, but
  // pull it inside the viewport if that would clip the left side.
  const right = Math.max(
    8,
    Math.min(viewportWidth - anchor.right, viewportWidth - MENU_WIDTH - 8),
  );

  return createPortal(
    <div
      ref={menuRef}
      role="menu"
      className="fixed z-50 w-44 rounded-md border bg-popover py-1 text-sm text-popover-foreground shadow-md"
      style={{ top, right }}
    >
      <button
        type="button"
        role="menuitem"
        onClick={onRename}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted"
      >
        <Pencil className="size-4" />
        <span>Rename</span>
      </button>
      <button
        type="button"
        role="menuitem"
        onClick={onDelete}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-destructive hover:bg-destructive/10"
      >
        <Trash2 className="size-4" />
        <span>Delete</span>
      </button>
    </div>,
    document.body,
  );
}

function RenameSessionDialog({
  session,
  onClose,
  onRenamed,
}: {
  session: ChatSession | null;
  onClose: () => void;
  onRenamed: (updated: {
    bot: string;
    id: string;
    custom_name: string | null;
  }) => void;
}) {
  const [name, setName] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    setName(session?.custom_name ?? "");
  }, [session]);

  const handleSave = async () => {
    if (!session) return;
    setSubmitting(true);
    try {
      const resp = await fetch(
        `/api/chat/sessions/${encodeURIComponent(session.bot)}/${encodeURIComponent(session.id)}/rename`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        },
      );
      if (!resp.ok) return;
      const data = (await resp.json()) as { custom_name: string | null };
      onRenamed({ bot: session.bot, id: session.id, custom_name: data.custom_name });
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={!!session} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Rename chat</DialogTitle>
          <DialogDescription className="text-xs">
            Leave blank to remove the custom name.
          </DialogDescription>
        </DialogHeader>
        <input
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="e.g. economy questions"
          maxLength={64}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          autoFocus
        />
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={submitting}>
            {submitting ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeleteSessionDialog({
  session,
  onClose,
  onDeleted,
}: {
  session: ChatSession | null;
  onClose: () => void;
  onDeleted: (deleted: { bot: string; id: string }) => void;
}) {
  const [submitting, setSubmitting] = React.useState(false);
  const handleDelete = async () => {
    if (!session) return;
    setSubmitting(true);
    try {
      const resp = await fetch(
        `/api/chat/sessions/${encodeURIComponent(session.bot)}/${encodeURIComponent(session.id)}`,
        { method: "DELETE" },
      );
      if (!resp.ok) return;
      onDeleted({ bot: session.bot, id: session.id });
      onClose();
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <Dialog open={!!session} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Delete chat?</DialogTitle>
          <DialogDescription>
            This permanently removes the session and its workspace files.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={submitting}
          >
            {submitting ? "Deleting…" : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
