"use client";

import * as React from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
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
// Note: DialogHeader is still used by the slash command + bot picker
// flows below; the workspace sheet drops it because WorkspaceTree
// provides its own header.
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
  /**
   * Slash commands like ``/send`` return a downloadable file
   * alongside (or instead of) text. Mirrors the desktop chat-view
   * field so we render a download chip on the assistant bubble.
   */
  commandFile?: {
    name: string;
    path: string;
    url: string;
  } | null;
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

  // Auto-scroll to bottom. On first paint (entering a chat with an
  // existing transcript) jump instantly so the user lands on the most
  // recent message instead of watching a long smooth-scroll animation
  // crawl through history. Subsequent updates (new messages / stream
  // chunks) stay smooth.
  const firstScrollRef = React.useRef(true);
  React.useLayoutEffect(() => {
    if (!messagesEndRef.current) return;
    if (firstScrollRef.current) {
      messagesEndRef.current.scrollIntoView({
        behavior: "instant" as ScrollBehavior,
        block: "end",
      });
      firstScrollRef.current = false;
      return;
    }
    messagesEndRef.current.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
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
        .map((p) => {
          // ``uploaded.path`` is the stored ``uploads/<uuid>__<name>``
          // form. The file-serving endpoint expects just the
          // ``<uuid>__<name>`` portion, so strip the ``uploads/``
          // prefix once and pass that to both ``real_name`` and
          // ``attachmentUrl``. Previous revisions used
          // ``display_name`` which is the original (user-friendly)
          // filename — those links pointed at non-existent files
          // until the chat was reloaded from server history.
          const realName = p.uploaded!.path.startsWith("uploads/")
            ? p.uploaded!.path.slice("uploads/".length)
            : p.uploaded!.path;
          return {
            display_name: p.uploaded!.display_name,
            real_name: realName,
            mime: p.uploaded!.mime,
            url: attachmentUrl(session.bot, session.id, realName),
          };
        }),
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
      // Skip the assistant bubble only when both text *and* file are
      // empty (e.g. ``AbortError`` early return). ``/send <filename>``
      // returns empty text + a non-null ``commandFile``; we still
      // want a bubble so the user can tap the download chip.
      if (reply.text || reply.commandFile) {
        setMessages((prev) => [
          ...prev,
          {
            id: newId(),
            role: "assistant",
            content: reply.text,
            timestamp: new Date().toISOString(),
            commandFile: reply.commandFile ?? null,
          },
        ]);
      }
    } catch (error) {
      // Roll back the optimistic user bubble so the chat does not
      // silently swallow a failed send.
      setMessages((prev) => prev.filter((m) => m.id !== userMessage.id));
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
    <div className="flex h-full min-w-0 flex-col overflow-x-hidden">
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
            <li className="flex min-w-0 justify-start">
              <div className="min-w-0 max-w-[85%] overflow-hidden rounded-2xl bg-muted px-3 py-2 text-sm">
                {activeStream.text ? (
                  <MarkdownBody content={activeStream.text} />
                ) : (
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
            className="flex-1 resize-none rounded-2xl border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring [&::-webkit-scrollbar]:hidden"
            style={{
              maxHeight: "160px",
              scrollbarWidth: "none",
              msOverflowStyle: "none",
            }}
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

      {/* Workspace sheet. ``WorkspaceTree`` already renders its own
          header (title + Finder / Refresh / Close), so we strip the
          Dialog's default chrome — no DialogHeader, no built-in close
          X — to avoid a duplicated "Workspace" title and a second close
          button next to WorkspaceTree's own. ``DialogTitle`` stays in
          sr-only form so screen readers still announce the sheet. */}
      <Dialog
        open={workspaceOpen}
        onOpenChange={(open) => setWorkspaceOpen(open)}
      >
        <DialogContent
          className="h-[90vh] max-w-md overflow-hidden p-0"
          showCloseButton={false}
        >
          <DialogTitle className="sr-only">Workspace</DialogTitle>
          <DialogDescription className="sr-only">
            Files for {session.bot} session {session.id}
          </DialogDescription>
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
    <li className={`flex min-w-0 ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`min-w-0 max-w-[85%] overflow-hidden rounded-2xl px-3 py-2 text-sm ${
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground"
        }`}
      >
        {isUser ? (
          <div className="whitespace-pre-wrap">{message.content}</div>
        ) : (
          <MarkdownBody content={message.content} />
        )}
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
        {message.commandFile ? (
          <div className="mt-2">
            <a
              href={message.commandFile.url}
              target="_blank"
              rel="noopener noreferrer"
              download={message.commandFile.name}
              className="inline-flex items-center gap-2 rounded-md border bg-background/30 px-2 py-1 text-xs text-current underline-offset-2 hover:underline"
            >
              ⬇️ {message.commandFile.name}
            </a>
          </div>
        ) : null}
        <div className="mt-1 text-right text-[10px] opacity-60">
          {formatTime(message.timestamp)}
        </div>
      </div>
    </li>
  );
}

/**
 * Assistant messages may contain GitHub-flavored markdown (headings,
 * fenced code, lists, links). We share the desktop chat's
 * ``prose prose-sm`` tailwind-typography setup so the typography
 * looks the same on both surfaces. ``break-words`` +
 * ``[overflow-wrap:anywhere]`` keep long URLs / Korean text from
 * blowing past the bubble width on narrow phones.
 */
function MarkdownBody({ content }: { content: string }) {
  // ``min-w-0`` lets this flex/grid child actually shrink below its
  // content's intrinsic width. ``break-words`` +
  // ``[overflow-wrap:anywhere]`` break long unbreakable strings
  // (URLs, Korean blobs without spaces) instead of pushing the
  // bubble wider. ``<pre>`` blocks get their own ``overflow-x-auto``
  // so a wide code line scrolls within the bubble — never the
  // whole page. Tables get the same treatment.
  return (
    <div className="prose prose-sm dark:prose-invert min-w-0 max-w-full break-words [overflow-wrap:anywhere] prose-pre:my-2 prose-pre:max-w-full prose-pre:overflow-x-auto prose-pre:rounded-md prose-pre:bg-background/40 prose-pre:p-2 prose-code:break-words prose-img:max-w-full prose-table:block prose-table:max-w-full prose-table:overflow-x-auto prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1 prose-li:my-0">
      <ReactMarkdown>{content || ""}</ReactMarkdown>
    </div>
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

