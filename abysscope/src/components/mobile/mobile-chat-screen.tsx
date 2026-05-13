"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowUp,
  Folder,
  Menu as MenuIcon,
  Mic,
  Paperclip,
  Slash,
  X,
} from "lucide-react";
import { BotAvatar } from "@/components/bot-avatar";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { WorkspaceTree } from "@/components/chat/workspace-tree";
import {
  ALLOWED_UPLOAD_MIME_TYPES,
  MAX_UPLOADS_PER_MESSAGE,
  attachmentUrl,
  uploadAttachment,
  type BotSummary,
  type ChatMessage,
  type ChatSession,
  type SlashCommandSpec,
  type UploadedAttachment,
} from "@/lib/abyss-api";
import {
  getSessionStream,
  useMultiSessionChatStream,
} from "@/components/chat/use-chat-stream";

interface Props {
  bots: BotSummary[];
  session: ChatSession;
  initialMessages: ChatMessage[];
}

interface ConversationMessage extends ChatMessage {
  id: string;
  streaming?: boolean;
}

interface PendingAttachment {
  localId: string;
  file: File;
  uploaded?: UploadedAttachment;
  uploading: boolean;
  error?: string;
}

const ALLOWED_SET = new Set<string>(ALLOWED_UPLOAD_MIME_TYPES);

function newId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function sessionLabel(session: ChatSession): string {
  return (
    session.custom_name?.trim() ||
    session.bot_display_name ||
    session.bot
  );
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

// ---------------------------------------------------------------------------
// Screen
// ---------------------------------------------------------------------------

export function MobileChatScreen({ bots, session, initialMessages }: Props) {
  const [messages, setMessages] = React.useState<ConversationMessage[]>(
    () => initialMessages.map((m) => ({ ...m, id: newId() }))
  );
  const [draft, setDraft] = React.useState("");
  const [pending, setPending] = React.useState<PendingAttachment[]>([]);
  const [transientError, setTransientError] = React.useState<string | null>(
    null
  );
  const [workspaceOpen, setWorkspaceOpen] = React.useState(false);
  const [slashOpen, setSlashOpen] = React.useState(false);
  const [slashCommands, setSlashCommands] = React.useState<
    SlashCommandSpec[] | null
  >(null);

  const messagesEndRef = React.useRef<HTMLDivElement | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);

  const stream = useMultiSessionChatStream();
  const activeStream = getSessionStream(stream.streams, session.id);

  // Auto-scroll to bottom on new messages / streaming chunks.
  React.useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeStream.text, activeStream.streaming]);

  // Auto-grow textarea up to a sensible cap so the input bar does not
  // eat the entire viewport on multi-line drafts.
  React.useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [draft]);

  const hasText = draft.trim().length > 0;
  const hasPending = pending.some((p) => p.uploading);
  const sendable = (hasText || pending.some((p) => p.uploaded)) && !hasPending;

  const updatePending = React.useCallback(
    (localId: string, patch: Partial<PendingAttachment>) => {
      setPending((prev) =>
        prev.map((item) =>
          item.localId === localId ? { ...item, ...patch } : item
        )
      );
    },
    []
  );

  const removePending = React.useCallback((localId: string) => {
    setPending((prev) => prev.filter((item) => item.localId !== localId));
  }, []);

  const enqueueFile = React.useCallback(
    async (file: File) => {
      if (!ALLOWED_SET.has(file.type)) {
        setTransientError(
          `Unsupported type: ${file.type || "unknown"}. Allowed: ${ALLOWED_UPLOAD_MIME_TYPES.join(", ")}`
        );
        return;
      }
      const localId = newId();
      setPending((prev) => [
        ...prev,
        { localId, file, uploading: true },
      ]);
      try {
        const uploaded = await uploadAttachment(
          session.bot,
          session.id,
          file
        );
        updatePending(localId, { uploaded, uploading: false });
      } catch (error) {
        updatePending(localId, {
          uploading: false,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    },
    [session.bot, session.id, updatePending]
  );

  const addFiles = React.useCallback(
    (fileList: FileList | File[]) => {
      setTransientError(null);
      const incoming = Array.from(fileList);
      if (pending.length + incoming.length > MAX_UPLOADS_PER_MESSAGE) {
        setTransientError(
          `Up to ${MAX_UPLOADS_PER_MESSAGE} files per message`
        );
        return;
      }
      incoming.forEach(enqueueFile);
    },
    [pending.length, enqueueFile]
  );

  const handleSend = async () => {
    if (!sendable) return;
    const text = draft.trim();
    const attachmentPaths = pending
      .map((p) => p.uploaded?.path)
      .filter((path): path is string => !!path);
    const display = text || "(attachments)";

    const userMessage: ConversationMessage = {
      id: newId(),
      role: "user",
      content: display,
      timestamp: new Date().toISOString(),
      attachments: pending
        .filter((p) => p.uploaded)
        .map((p) => ({
          display_name: p.uploaded!.display_name,
          real_name: p.uploaded!.path,
          mime: p.uploaded!.mime,
          url: attachmentUrl(session.bot, session.id, p.uploaded!.display_name),
        })),
    };
    setMessages((prev) => [...prev, userMessage]);
    setDraft("");
    setPending([]);

    try {
      const reply = await stream.send(
        session.bot,
        session.id,
        display,
        attachmentPaths
      );
      if (reply) {
        setMessages((prev) => [
          ...prev,
          {
            id: newId(),
            role: "assistant",
            content: reply,
            timestamp: new Date().toISOString(),
          },
        ]);
      }
    } catch (error) {
      setTransientError(
        error instanceof Error ? error.message : String(error)
      );
    }
  };

  const handleSlashOpen = async () => {
    setSlashOpen(true);
    if (slashCommands === null) {
      try {
        const response = await fetch("/api/chat/commands");
        if (response.ok) {
          const body = await response.json();
          setSlashCommands(body.commands ?? []);
        }
      } catch {
        // ignore; the sheet shows an empty state if the fetch fails
      }
    }
  };

  const handleSlashPick = (spec: SlashCommandSpec) => {
    setDraft(`/${spec.name} `);
    setSlashOpen(false);
    requestAnimationFrame(() => textareaRef.current?.focus());
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && event.ctrlKey) {
      event.preventDefault();
      handleSend();
    }
  };

  const botSummary =
    bots.find((b) => b.name === session.bot) ?? {
      name: session.bot,
      display_name: session.bot_display_name || session.bot,
      type: "claude_code",
    };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <header className="flex h-14 shrink-0 items-center gap-2 border-b px-3">
        <Link
          href="/mobile/sessions"
          aria-label="Back to sessions"
          className="rounded-md p-2 hover:bg-muted"
        >
          <MenuIcon className="size-5" />
        </Link>
        <BotAvatar
          botName={session.bot}
          displayName={botSummary.display_name}
          size="sm"
        />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">
            {sessionLabel(session)}
          </div>
          <div className="truncate text-xs text-muted-foreground">
            {botSummary.display_name}
          </div>
        </div>
        <button
          type="button"
          aria-label="Workspace files"
          className="rounded-md p-2 hover:bg-muted"
          onClick={() => setWorkspaceOpen(true)}
        >
          <Folder className="size-5" />
        </button>
      </header>

      {/* Messages */}
      <main className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
        {messages.length === 0 && !activeStream.streaming && (
          <p className="mt-8 text-center text-sm text-muted-foreground">
            Send a message to start the conversation.
          </p>
        )}
        <ul className="space-y-3">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
          {activeStream.streaming && (
            <li className="flex justify-start">
              <div className="max-w-[85%] rounded-2xl bg-muted px-3 py-2 text-sm">
                {activeStream.text || (
                  <span className="text-muted-foreground">…</span>
                )}
              </div>
            </li>
          )}
          {activeStream.error && (
            <li className="text-center text-xs text-destructive">
              {activeStream.error}
            </li>
          )}
        </ul>
        <div ref={messagesEndRef} />
      </main>

      {/* Pending attachments */}
      {pending.length > 0 && (
        <div className="flex shrink-0 gap-2 overflow-x-auto border-t bg-muted/40 px-3 py-2">
          {pending.map((item) => (
            <PendingAttachmentChip
              key={item.localId}
              attachment={item}
              onRemove={() => removePending(item.localId)}
            />
          ))}
        </div>
      )}

      {transientError && (
        <div className="shrink-0 border-t bg-destructive/10 px-3 py-1 text-xs text-destructive">
          {transientError}
        </div>
      )}

      {/* Input bar */}
      <footer className="shrink-0 border-t bg-background">
        <div className="flex items-end gap-1 px-2 py-2">
          <button
            type="button"
            aria-label="Slash commands"
            className="rounded-full p-2 text-muted-foreground hover:bg-muted"
            onClick={handleSlashOpen}
          >
            <Slash className="size-5" />
          </button>
          <button
            type="button"
            aria-label="Attach file"
            className="rounded-full p-2 text-muted-foreground hover:bg-muted"
            onClick={() => fileInputRef.current?.click()}
          >
            <Paperclip className="size-5" />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ALLOWED_UPLOAD_MIME_TYPES.join(",")}
            className="hidden"
            onChange={(event) => {
              if (event.target.files) addFiles(event.target.files);
              event.target.value = "";
            }}
          />
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="메시지 작성…"
            rows={1}
            className="flex-1 resize-none rounded-2xl border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
            style={{ maxHeight: "160px" }}
          />
          {hasText || pending.some((p) => p.uploaded) ? (
            <button
              type="button"
              aria-label="Send message"
              disabled={!sendable || activeStream.streaming}
              onClick={handleSend}
              className="rounded-full bg-primary p-2 text-primary-foreground disabled:opacity-50"
            >
              <ArrowUp className="size-5" />
            </button>
          ) : (
            <button
              type="button"
              aria-label="Voice (coming soon)"
              disabled
              className="rounded-full p-2 text-muted-foreground"
              title="Voice mode lands in a later phase"
            >
              <Mic className="size-5" />
            </button>
          )}
        </div>
      </footer>

      {/* Workspace sheet */}
      <Dialog
        open={workspaceOpen}
        onOpenChange={(open) => setWorkspaceOpen(open)}
      >
        <DialogContent className="h-[90vh] max-w-md p-0">
          <DialogHeader className="border-b px-4 py-3">
            <DialogTitle>Workspace</DialogTitle>
            <DialogDescription className="text-xs">
              {session.bot} · {session.id}
            </DialogDescription>
          </DialogHeader>
          <div className="h-full overflow-hidden">
            <WorkspaceTree
              bot={session.bot}
              sessionId={session.id}
              onClose={() => setWorkspaceOpen(false)}
            />
          </div>
        </DialogContent>
      </Dialog>

      {/* Slash command sheet */}
      <Dialog
        open={slashOpen}
        onOpenChange={(open) => setSlashOpen(open)}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Slash commands</DialogTitle>
            <DialogDescription className="text-xs">
              Pick one to insert it into the input.
            </DialogDescription>
          </DialogHeader>
          <SlashCommandList
            commands={slashCommands}
            onPick={handleSlashPick}
            onClose={() => setSlashOpen(false)}
          />
        </DialogContent>
      </Dialog>

      {/* Active-stream cancel button */}
      {activeStream.streaming && (
        <button
          type="button"
          onClick={() => stream.cancel(session.id)}
          className="fixed bottom-20 left-1/2 -translate-x-1/2 rounded-full bg-secondary px-3 py-1 text-xs text-secondary-foreground shadow"
        >
          Stop
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pieces
// ---------------------------------------------------------------------------

function MessageBubble({ message }: { message: ConversationMessage }) {
  const isUser = message.role === "user";
  return (
    <li className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap ${
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground"
        }`}
      >
        {message.content}
        {message.attachments?.length ? (
          <div className="mt-2 flex flex-wrap gap-2">
            {message.attachments.map((att) => (
              <a
                key={att.real_name}
                href={att.url}
                target="_blank"
                rel="noreferrer"
                className="rounded-md border bg-background/30 px-2 py-1 text-xs text-current underline-offset-2 hover:underline"
              >
                📎 {att.display_name}
              </a>
            ))}
          </div>
        ) : null}
        <div className="mt-1 text-right text-[10px] opacity-60">
          {formatTime(message.timestamp)}
        </div>
      </div>
    </li>
  );
}

function PendingAttachmentChip({
  attachment,
  onRemove,
}: {
  attachment: PendingAttachment;
  onRemove: () => void;
}) {
  return (
    <div className="relative flex items-center gap-2 rounded-md border bg-background px-2 py-1 text-xs">
      <span className="max-w-[120px] truncate">{attachment.file.name}</span>
      {attachment.uploading && (
        <span className="text-muted-foreground">…</span>
      )}
      {attachment.error && (
        <span className="text-destructive">!</span>
      )}
      <button
        type="button"
        onClick={onRemove}
        className="ml-1 text-muted-foreground hover:text-foreground"
        aria-label="Remove attachment"
      >
        <X className="size-3" />
      </button>
    </div>
  );
}

function SlashCommandList({
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

