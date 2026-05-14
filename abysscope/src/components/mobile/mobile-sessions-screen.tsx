"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Menu } from "@base-ui/react/menu";
import {
  AlertCircle,
  MessageSquarePlus,
  Pencil,
  Trash2,
  X,
} from "lucide-react";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { BotAvatar } from "@/components/bot-avatar";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { BotSummary, ChatSession } from "@/lib/abyss-api";

// Client components must hit the Next.js proxy routes (``/api/chat/...``)
// instead of ``abyss-api`` helpers that point at ``127.0.0.1:3848``.
// From a phone, ``127.0.0.1`` is the *phone's* loopback and the
// request silently dies. The dashboard server (Mac) is the only one
// that can reach the sidecar directly, so all reads/writes go through
// its proxy routes.

async function fetchSessions(bot: string): Promise<ChatSession[]> {
  const response = await fetch(
    `/api/chat/sessions?bot=${encodeURIComponent(bot)}`
  );
  if (!response.ok) return [];
  const data = (await response.json()) as { sessions: ChatSession[] };
  return data.sessions;
}

async function createSession(bot: string): Promise<ChatSession> {
  const response = await fetch("/api/chat/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bot }),
  });
  if (!response.ok) {
    throw new Error(`createSession failed: ${response.status}`);
  }
  return (await response.json()) as ChatSession;
}

async function deleteSession(bot: string, id: string): Promise<void> {
  const response = await fetch(
    `/api/chat/sessions/${encodeURIComponent(bot)}/${encodeURIComponent(id)}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    throw new Error(`deleteSession failed: ${response.status}`);
  }
}

async function renameSession(
  bot: string,
  id: string,
  name: string
): Promise<{ custom_name: string | null }> {
  const response = await fetch(
    `/api/chat/sessions/${encodeURIComponent(bot)}/${encodeURIComponent(id)}/rename`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }
  );
  if (!response.ok) {
    throw new Error(`renameSession failed: ${response.status}`);
  }
  return (await response.json()) as { custom_name: string | null };
}

interface Props {
  apiOnline: boolean;
  bots: BotSummary[];
}

function formatRelative(iso: string): string {
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return "";
  const now = Date.now();
  const diffMs = now - ts;
  const diffMinutes = Math.floor(diffMs / 60_000);

  if (diffMinutes < 1) return "방금";
  if (diffMinutes < 60) return `${diffMinutes}분`;

  const then = new Date(ts);
  const sameDay =
    then.toDateString() === new Date(now).toDateString();
  if (sameDay) {
    return then.toLocaleTimeString("ko-KR", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }
  return `${then.getMonth() + 1}.${then.getDate()}`;
}

function sessionLabel(session: ChatSession): string {
  if (session.custom_name && session.custom_name.trim()) {
    return session.custom_name;
  }
  return session.bot_display_name || session.bot;
}

// ---------------------------------------------------------------------------
// Long-press helper
// ---------------------------------------------------------------------------

interface LongPressOptions {
  onLongPress: () => void;
  delayMs?: number;
}

function useLongPress({ onLongPress, delayMs = 500 }: LongPressOptions) {
  const timerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const start = React.useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      onLongPress();
      timerRef.current = null;
    }, delayMs);
  }, [onLongPress, delayMs]);

  const cancel = React.useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  return {
    onTouchStart: start,
    onTouchEnd: cancel,
    onTouchMove: cancel,
    onTouchCancel: cancel,
    onContextMenu: (event: React.SyntheticEvent) => {
      // Desktop / Safari right-click also opens the action sheet for
      // testing without a touchscreen.
      event.preventDefault();
      onLongPress();
    },
  };
}

// ---------------------------------------------------------------------------
// Screen
// ---------------------------------------------------------------------------

export function MobileSessionsScreen({ apiOnline, bots }: Props) {
  const router = useRouter();
  const [sessions, setSessions] = React.useState<ChatSession[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);

  const [actionSession, setActionSession] = React.useState<ChatSession | null>(
    null
  );
  const [renameSession, setRenameSession] = React.useState<ChatSession | null>(
    null
  );
  const [deleteSession, setDeleteSession] = React.useState<ChatSession | null>(
    null
  );

  const reload = React.useCallback(async () => {
    if (!apiOnline || bots.length === 0) {
      setSessions([]);
      return;
    }
    setLoading(true);
    setErrorMessage(null);
    try {
      const results = await Promise.all(
        bots.map((bot) => fetchSessions(bot.name).catch(() => []))
      );
      const merged = results
        .flat()
        .sort((a, b) =>
          b.updated_at.localeCompare(a.updated_at)
        );
      setSessions(merged);
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to load sessions"
      );
    } finally {
      setLoading(false);
    }
  }, [apiOnline, bots]);

  React.useEffect(() => {
    reload();
  }, [reload]);

  const handleCreate = async (botName: string) => {
    try {
      const created = await createSession(botName);
      router.push(`/mobile/chat/${botName}/${created.id}`);
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to create chat"
      );
    }
  };

  const handleSelect = (session: ChatSession) => {
    router.push(`/mobile/chat/${session.bot}/${session.id}`);
  };

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 items-center justify-between border-b px-4">
        <h1 className="text-base font-semibold">Abyss</h1>
        <Menu.Root>
          <Menu.Trigger
            disabled={!apiOnline || bots.length === 0}
            render={
              <Button size="sm" variant="default">
                <MessageSquarePlus className="size-4" />
                New
              </Button>
            }
          />
          <Menu.Portal>
            <Menu.Positioner sideOffset={6} align="end">
              <Menu.Popup className="z-50 min-w-[220px] rounded-md border bg-popover p-1 text-sm shadow-md outline-none">
                {bots.map((bot) => (
                  <Menu.Item
                    key={bot.name}
                    onClick={() => handleCreate(bot.name)}
                    className="flex cursor-pointer items-center gap-2 rounded-sm px-2 py-2 outline-none data-highlighted:bg-muted"
                  >
                    <BotAvatar
                      botName={bot.name}
                      displayName={bot.display_name}
                      size="sm"
                    />
                    <span className="truncate">{bot.display_name}</span>
                  </Menu.Item>
                ))}
              </Menu.Popup>
            </Menu.Positioner>
          </Menu.Portal>
        </Menu.Root>
      </header>

      <main className="flex-1 overflow-y-auto">
        {!apiOnline && (
          <div className="p-4">
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Chat backend unreachable</AlertTitle>
              <AlertDescription>
                The internal chat server is not responding. Make sure
                <code className="px-1">abyss start</code> is running on your
                Mac and Tailscale (if used) is connected.
              </AlertDescription>
            </Alert>
          </div>
        )}

        {errorMessage && (
          <div className="p-4">
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Error</AlertTitle>
              <AlertDescription>{errorMessage}</AlertDescription>
            </Alert>
          </div>
        )}

        {apiOnline && sessions.length === 0 && !loading && (
          <div className="p-8 text-center text-sm text-muted-foreground">
            No chats yet. Tap <span className="font-semibold">New</span> to
            start one.
          </div>
        )}

        <ul>
          {sessions.map((session) => (
            <SessionRow
              key={`${session.bot}:${session.id}`}
              session={session}
              onSelect={() => handleSelect(session)}
              onLongPress={() => setActionSession(session)}
            />
          ))}
        </ul>

        {loading && (
          <div className="p-4 text-center text-xs text-muted-foreground">
            Loading…
          </div>
        )}
      </main>

      {/* Long-press action sheet */}
      <Dialog
        open={!!actionSession}
        onOpenChange={(open) => !open && setActionSession(null)}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="truncate">
              {actionSession ? sessionLabel(actionSession) : ""}
            </DialogTitle>
            <DialogDescription className="text-xs">
              {actionSession?.id}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Button
              variant="outline"
              className="justify-start"
              onClick={() => {
                setRenameSession(actionSession);
                setActionSession(null);
              }}
            >
              <Pencil className="mr-2 size-4" />
              Rename
            </Button>
            <Button
              variant="outline"
              className="justify-start text-destructive"
              onClick={() => {
                setDeleteSession(actionSession);
                setActionSession(null);
              }}
            >
              <Trash2 className="mr-2 size-4" />
              Delete
            </Button>
            <Button
              variant="ghost"
              className="justify-start"
              onClick={() => setActionSession(null)}
            >
              <X className="mr-2 size-4" />
              Cancel
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <RenameDialog
        session={renameSession}
        onClose={() => setRenameSession(null)}
        onSaved={(updated) => {
          setSessions((prev) =>
            prev.map((s) =>
              s.bot === updated.bot && s.id === updated.id
                ? { ...s, custom_name: updated.custom_name }
                : s
            )
          );
        }}
      />

      <DeleteDialog
        session={deleteSession}
        onClose={() => setDeleteSession(null)}
        onDeleted={(deleted) => {
          setSessions((prev) =>
            prev.filter(
              (s) => !(s.bot === deleted.bot && s.id === deleted.id)
            )
          );
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Row
// ---------------------------------------------------------------------------

function SessionRow({
  session,
  onSelect,
  onLongPress,
}: {
  session: ChatSession;
  onSelect: () => void;
  onLongPress: () => void;
}) {
  const longPress = useLongPress({ onLongPress });
  return (
    <li className="border-b">
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-3 text-left active:bg-muted"
        onClick={onSelect}
        {...longPress}
      >
        <BotAvatar
          botName={session.bot}
          displayName={session.bot_display_name || session.bot}
          size="md"
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="truncate text-sm font-medium">
              {sessionLabel(session)}
            </span>
            <span className="shrink-0 text-xs text-muted-foreground">
              {formatRelative(session.updated_at)}
            </span>
          </div>
          <div className="truncate text-xs text-muted-foreground">
            {session.preview || "(no messages yet)"}
          </div>
        </div>
      </button>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Rename dialog
// ---------------------------------------------------------------------------

function RenameDialog({
  session,
  onClose,
  onSaved,
}: {
  session: ChatSession | null;
  onClose: () => void;
  onSaved: (updated: {
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
      const updated = await renameSession(session.bot, session.id, name);
      onSaved({
        bot: session.bot,
        id: session.id,
        custom_name: updated.custom_name,
      });
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={!!session}
      onOpenChange={(open) => !open && onClose()}
    >
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
          placeholder="e.g. 경제질문"
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

// ---------------------------------------------------------------------------
// Delete confirm dialog
// ---------------------------------------------------------------------------

function DeleteDialog({
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
      await deleteSession(session.bot, session.id);
      onDeleted({ bot: session.bot, id: session.id });
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={!!session}
      onOpenChange={(open) => !open && onClose()}
    >
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
