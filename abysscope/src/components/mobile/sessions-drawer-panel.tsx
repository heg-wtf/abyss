"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { MessageSquarePlus, MoreVertical } from "lucide-react";
import { BotAvatar } from "@/components/bot-avatar";
import {
  getSessionStream,
  useMultiSessionChatStream,
} from "@/components/chat/use-chat-stream";
import { setUnreadBadge } from "@/lib/abyss-api";
import type {
  BotSummary,
  ChatSession,
  RoutineSummary,
} from "@/lib/abyss-api";
import {
  DrawerFooter,
  RoutineKindIcon,
  TabButton,
} from "./sessions-drawer-bits";
import { SessionActionsPopover } from "./sessions-drawer-actions-popover";
import { RenameSessionDialog } from "./sessions-drawer-rename-dialog";
import { DeleteSessionDialog } from "./sessions-drawer-delete-dialog";

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
  // Subscribes to the module-level streaming store so the indicator
  // dot lights up the instant any session in the list flips into
  // streaming — including ones the user is not currently viewing.
  const stream = useMultiSessionChatStream();
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

  React.useEffect(() => {
    // Cancellation guard: opening + closing the drawer quickly over
    // a slow Tailscale connection used to fire ``setBots`` /
    // ``setSessions`` on an unmounted panel. ``cancelled`` short-
    // circuits every setter after unmount.
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      try {
        const botResp = await fetch("/api/chat/bots");
        const botData = botResp.ok ? await botResp.json() : { bots: [] };
        const botList: BotSummary[] = botData.bots ?? [];
        if (cancelled) return;
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
        if (cancelled) return;
        const merged = all
          .flat()
          .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
        setSessions(merged);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  // App-icon badge — sum of unread sessions + unread routines.
  // Recomputes whenever either list shifts (initial fetch, optimistic
  // tap, refresh). The helper itself no-ops in browsers that lack
  // ``setAppBadge`` so this is safe to call unconditionally.
  React.useEffect(() => {
    const unreadSessions = sessions.filter((s) => s.unread === true).length;
    const unreadRoutines = routines.filter((r) => r.unread === true).length;
    setUnreadBadge(unreadSessions + unreadRoutines);
  }, [sessions, routines]);

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
            routines.map((routine) => {
              const isUnread = routine.unread === true;
              return (
                <li key={`${routine.bot}:${routine.kind}:${routine.job_name}`}>
                  <button
                    type="button"
                    onClick={() => {
                      if (isUnread) {
                        setRoutines((prev) =>
                          prev.map((r) =>
                            r.bot === routine.bot &&
                            r.kind === routine.kind &&
                            r.job_name === routine.job_name
                              ? { ...r, unread: false }
                              : r,
                          ),
                        );
                      }
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
                      <div className="flex items-center gap-2 text-sm">
                        {isUnread && (
                          <span
                            aria-label="새 실행 결과"
                            title="새 실행 결과"
                            className="inline-block size-2 shrink-0 rounded-full bg-emerald-500"
                          />
                        )}
                        <RoutineKindIcon kind={routine.kind} />
                        <span
                          className={`truncate ${
                            isUnread
                              ? "font-semibold text-foreground"
                              : "font-medium"
                          }`}
                        >
                          {routine.job_name}
                        </span>
                      </div>
                      <div
                        className={`truncate text-xs ${
                          isUnread
                            ? "font-medium text-foreground"
                            : "text-muted-foreground"
                        }`}
                      >
                        {routine.preview || "(no runs yet)"}
                      </div>
                    </div>
                  </button>
                </li>
              );
            })
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
            const isStreaming = getSessionStream(stream.streams, sess.id).streaming;
            const isUnread = sess.unread === true && !isActive;
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
                      // Optimistic: hide unread dot immediately on
                      // tap. Server mark happens on detail mount.
                      if (sess.unread) {
                        setSessions((prev) =>
                          prev.map((s) =>
                            s.bot === sess.bot && s.id === sess.id
                              ? { ...s, unread: false }
                              : s,
                          ),
                        );
                      }
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
                      <div className="flex min-w-0 items-center gap-1.5">
                        {isStreaming ? (
                          <span
                            aria-label="진행중"
                            title="진행중"
                            className="inline-block size-1.5 shrink-0 rounded-full bg-emerald-500"
                            style={{
                              animation:
                                "stream-pulse 1.4s ease-in-out infinite",
                            }}
                          />
                        ) : isUnread ? (
                          <span
                            aria-label="새 메시지"
                            title="새 메시지"
                            className="inline-block size-2 shrink-0 rounded-full bg-emerald-500"
                          />
                        ) : null}
                        <div
                          className={`truncate text-sm ${
                            isUnread
                              ? "font-semibold text-foreground"
                              : "font-medium"
                          }`}
                        >
                          {label}
                        </div>
                      </div>
                      <div
                        className={`truncate text-xs ${
                          isUnread
                            ? "font-medium text-foreground"
                            : "text-muted-foreground"
                        }`}
                      >
                        {isStreaming
                          ? "응답 생성 중…"
                          : sess.preview || "(no messages yet)"}
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
