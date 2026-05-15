"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import {
  ArrowUp,
  Command,
  Folder,
  Menu as MenuIcon,
  Mic,
  Paperclip,
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
import { SessionsDrawerPanel } from "@/components/mobile/sessions-drawer-panel";
import { SlideDrawer } from "@/components/mobile/slide-drawer";
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
import { useVoiceMode, type VoiceState } from "@/components/chat/use-voice-mode";
import { VoiceScreen } from "@/components/chat/voice-screen";

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
  const [sessionsOpen, setSessionsOpen] = React.useState(false);
  const [slashOpen, setSlashOpen] = React.useState(false);
  const [voiceMode, setVoiceMode] = React.useState(false);
  const router = useRouter();
  const [slashCommands, setSlashCommands] = React.useState<
    SlashCommandSpec[] | null
  >(null);

  const messagesEndRef = React.useRef<HTMLDivElement | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);
  const isTouchDevice = useIsTouchDevice();

  const stream = useMultiSessionChatStream();
  const activeStream = getSessionStream(stream.streams, session.id);

  // Voice mode — taps the mic, transcribes via ElevenLabs Scribe,
  // and runs the full conversational loop: speak → auto-submit with
  // ``voice_mode: true`` → assistant reply auto-TTS'd → recording
  // auto-restarts. Mirrors the desktop chat-view pattern (removed in
  // commit c983c9b) inside a mobile full-screen overlay.
  const voice = useVoiceMode({
    onTranscript: (text) => {
      void submitTranscript(text);
    },
  });

  // Swipe gesture: drag left = next chat, drag right = previous.
  // The chat page loads the active bot's sessions on demand so the
  // swipe targets stay in sync with the sessions drawer.
  const [siblingSessions, setSiblingSessions] = React.useState<string[]>([]);
  React.useEffect(() => {
    let cancelled = false;
    fetch(`/api/chat/sessions?bot=${encodeURIComponent(session.bot)}`)
      .then((r) => (r.ok ? r.json() : { sessions: [] }))
      .then((data: { sessions: Array<{ id: string }> }) => {
        if (cancelled) return;
        setSiblingSessions(data.sessions.map((s) => s.id));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [session.bot, session.id]);

  const goToSibling = React.useCallback(
    (offset: -1 | 1) => {
      if (siblingSessions.length < 2) return;
      const index = siblingSessions.indexOf(session.id);
      if (index === -1) return;
      const next = siblingSessions[index + offset];
      if (!next) return;
      router.push(`/mobile/chat/${session.bot}/${next}`);
    },
    [siblingSessions, session.id, session.bot, router],
  );

  const swipeStartRef = React.useRef<{ x: number; y: number } | null>(null);
  const onMessagesTouchStart = (event: React.TouchEvent<HTMLElement>) => {
    const touch = event.touches[0];
    swipeStartRef.current = { x: touch.clientX, y: touch.clientY };
  };
  const onMessagesTouchEnd = (event: React.TouchEvent<HTMLElement>) => {
    const start = swipeStartRef.current;
    swipeStartRef.current = null;
    if (!start) return;
    const touch = event.changedTouches[0];
    const dx = touch.clientX - start.x;
    const dy = touch.clientY - start.y;
    // Horizontal-dominant + meaningful distance only. Threshold of
    // 80px keeps an accidental finger-drag from triggering a chat
    // switch when the user is just scrolling.
    if (Math.abs(dx) < 80) return;
    if (Math.abs(dx) < Math.abs(dy) * 1.5) return;
    goToSibling(dx > 0 ? -1 : 1);
  };

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

  /**
   * One-slot message queue. When the user hits Send while a reply is
   * already streaming, we keep their bubble optimistic and stash the
   * payload here; the streaming-falling-edge effect below flushes it as
   * soon as the current turn finishes. A new Send overwrites the slot
   * (single-message queue, à la Claude.ai), and the queued bubble
   * carries an explicit cancel control so the user can pull it back.
   */
  type QueuedSend = {
    userMessageId: string;
    display: string;
    attachmentPaths: string[];
    voiceFlag: boolean;
  };
  const [queued, setQueued] = React.useState<QueuedSend | null>(null);

  const executeStreamSend = React.useCallback(
    async (
      userMessageId: string,
      display: string,
      attachmentPaths: string[],
      voiceFlag = false,
    ) => {
      try {
        const reply = await stream.send(
          session.bot,
          session.id,
          display,
          attachmentPaths,
          voiceFlag,
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
        setMessages((prev) => prev.filter((m) => m.id !== userMessageId));
        setTransientError(
          error instanceof Error ? error.message : String(error)
        );
      }
    },
    [session.bot, session.id, stream]
  );

  // Falling-edge of streaming → flush a queued send, if any. The
  // previous revision *also* triggered voice TTS from this effect by
  // sampling ``messages[last]`` on the same render, but
  // ``streaming`` flips to ``false`` (inside ``stream.send``'s
  // ``finally``) one render before ``messages`` gains the assistant
  // bubble (which lives in the ``await stream.send`` continuation).
  // The effect fired once on the streaming flip with ``last`` still
  // being the user message, unconditionally bumped
  // ``previousStreamingRef.current`` to ``false``, then fired again
  // when ``messages`` updated — but by then ``wasStreaming`` was
  // already ``false`` and the speak branch never ran. Voice mode
  // got stuck on the "processing" label forever.
  //
  // The fix moved auto-TTS out into its own ``messages``-keyed
  // effect below. This one keeps the queue-flush behaviour intact.
  const previousStreamingRef = React.useRef(activeStream.streaming);
  React.useEffect(() => {
    const wasStreaming = previousStreamingRef.current;
    previousStreamingRef.current = activeStream.streaming;
    if (!wasStreaming || activeStream.streaming) return;
    if (!queued) return;
    const next = queued;
    setQueued(null);
    void executeStreamSend(
      next.userMessageId,
      next.display,
      next.attachmentPaths,
      next.voiceFlag,
    );
  }, [activeStream.streaming, queued, executeStreamSend]);

  // Auto-TTS the latest assistant reply while voice mode is on.
  // Triggered by ``messages`` changing rather than the streaming
  // flag flipping so we don't race with the streaming/messages
  // update order (see the comment block above).
  //
  // When voice mode just opened we **seed** ``lastSpokenMessageIdRef``
  // to the current last message id. That stops the effect from
  // speaking whatever historical assistant reply happens to be the
  // last bubble in chat history — the user reported "마이크 다시
  // 누르면 이전 응답이 들리는 경우". Only messages that arrive
  // *after* voice mode opened get spoken.
  const lastSpokenMessageIdRef = React.useRef<string | null>(null);
  const previousVoiceModeRef = React.useRef(voiceMode);
  React.useEffect(() => {
    const wasVoiceMode = previousVoiceModeRef.current;
    previousVoiceModeRef.current = voiceMode;

    if (!voiceMode) {
      // Voice mode off → release the dedup so the next open starts
      // fresh.
      lastSpokenMessageIdRef.current = null;
      return;
    }
    if (!wasVoiceMode) {
      // Voice mode just opened → mark the current tail as
      // "already spoken" so we never replay history.
      const last = messages[messages.length - 1];
      lastSpokenMessageIdRef.current = last?.id ?? null;
      return;
    }
    if (activeStream.streaming) return;
    const last = messages[messages.length - 1];
    if (!last || last.role !== "assistant" || !last.content) return;
    if (lastSpokenMessageIdRef.current === last.id) return;
    lastSpokenMessageIdRef.current = last.id;
    void voice.speak(last.content);
  }, [messages, voiceMode, activeStream.streaming, voice]);

  // Auto-restart recording after the assistant TTS reply finishes.
  // ``speaking → idle`` transition with ``voiceMode`` still active
  // means the user just heard the reply; reopen the mic for the
  // next turn. Closing the overlay flips ``voiceMode`` to false
  // first, so this effect no-ops in that case.
  const prevVoiceStateRef = React.useRef<VoiceState>("idle");
  React.useEffect(() => {
    const prev = prevVoiceStateRef.current;
    prevVoiceStateRef.current = voice.voiceState;
    if (prev === "speaking" && voice.voiceState === "idle" && voiceMode) {
      void voice.start();
    }
  }, [voice.voiceState, voiceMode, voice]);

  const submitTranscript = React.useCallback(
    async (rawText: string) => {
      const text = rawText.trim();
      if (!text) return;
      const userMessage: ConversationMessage = {
        id: newId(),
        role: "user",
        content: text,
        timestamp: new Date().toISOString(),
      };
      if (activeStream.streaming) {
        setMessages((prev) => {
          const withoutOldQueue = queued
            ? prev.filter((m) => m.id !== queued.userMessageId)
            : prev;
          return [...withoutOldQueue, userMessage];
        });
        setQueued({
          userMessageId: userMessage.id,
          display: text,
          attachmentPaths: [],
          voiceFlag: true,
        });
        return;
      }
      setMessages((prev) => [...prev, userMessage]);
      await executeStreamSend(userMessage.id, text, [], true);
    },
    [activeStream.streaming, queued, executeStreamSend, setMessages, setQueued],
  );

  const handleVoiceOpen = React.useCallback(() => {
    setWorkspaceOpen(false);
    setSessionsOpen(false);
    setSlashOpen(false);
    setVoiceMode(true);
    void voice.start();
  }, [voice]);

  const handleVoiceClose = React.useCallback(() => {
    voice.cancel();
    setVoiceMode(false);
  }, [voice]);

  const cancelQueued = React.useCallback(() => {
    if (!queued) return;
    const targetId = queued.userMessageId;
    setMessages((prev) => prev.filter((m) => m.id !== targetId));
    setQueued(null);
  }, [queued, setMessages, setQueued]);

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

    // Streaming in progress — overwrite the single-slot queue. The
    // previous queued bubble (if any) is dropped so we never end up
    // with two pending sends fighting for the next turn.
    if (activeStream.streaming) {
      setMessages((prev) => {
        const withoutOldQueue = queued
          ? prev.filter((m) => m.id !== queued.userMessageId)
          : prev;
        return [...withoutOldQueue, userMessage];
      });
      setDraft("");
      setPending([]);
      setQueued({
        userMessageId: userMessage.id,
        display,
        attachmentPaths,
        voiceFlag: false,
      });
      return;
    }

    // Idle — fire immediately.
    setMessages((prev) => [...prev, userMessage]);
    setDraft("");
    setPending([]);
    await executeStreamSend(userMessage.id, display, attachmentPaths, false);
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

  /**
   * Enter-key semantics differ by device:
   *
   * - **Desktop / non-touch.** Enter sends, Shift+Enter inserts a newline.
   *   This matches the convention every modern web chat (Slack, Discord,
   *   Claude.ai, ChatGPT) uses on a real keyboard. Cmd/Ctrl+Enter also
   *   sends so muscle memory from the previous behavior keeps working.
   * - **Touch.** Enter always inserts a newline — the user has no easy
   *   modifier key, the send button is right next to the textarea, and
   *   accidental sends on the virtual keyboard are a worse failure than
   *   a missed newline. Cmd/Ctrl+Enter still sends for bluetooth keyboards.
   *
   * ``isComposing`` skips the IME confirm Enter (Hangul / Japanese
   * candidate selection) so the first key release after a composition
   * never triggers send.
   */
  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter") return;
    if (event.nativeEvent.isComposing) return;

    const isModifierEnter = event.ctrlKey || event.metaKey;
    if (isTouchDevice) {
      if (isModifierEnter) {
        event.preventDefault();
        void handleSend();
      }
      return;
    }
    if (event.shiftKey) return;
    event.preventDefault();
    void handleSend();
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
        <button
          type="button"
          onClick={() => setSessionsOpen(true)}
          aria-label="Open sessions"
          className="rounded-md p-2 hover:bg-muted"
        >
          <MenuIcon className="size-5" />
        </button>
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

      {/* Messages. Touch handlers turn a horizontal-dominant drag
          of ≥80 px into a chat switch — left→next, right→previous. */}
      <main
        className="min-h-0 flex-1 overflow-y-auto px-3 py-4"
        onTouchStart={onMessagesTouchStart}
        onTouchEnd={onMessagesTouchEnd}
      >
        {messages.length === 0 && !activeStream.streaming && (
          <p className="mt-8 text-center text-sm text-muted-foreground">
            Send a message to start the conversation.
          </p>
        )}
        <ul className="space-y-3">
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              queued={queued?.userMessageId === message.id}
              onCancelQueue={cancelQueued}
            />
          ))}
          {activeStream.streaming && (
            <li
              className="flex min-w-0 justify-start"
              role="status"
              aria-live="polite"
              aria-label="Assistant reply streaming"
            >
              <div className="min-w-0 max-w-[85%] overflow-hidden rounded-2xl bg-muted px-3 py-2 text-sm">
                {activeStream.text ? (
                  <>
                    <MarkdownBody content={activeStream.text} />
                    <StreamProgress
                      streaming={activeStream.streaming}
                      hasText
                      onCancel={() => stream.cancel(session.id)}
                    />
                  </>
                ) : (
                  <StreamProgress
                    streaming={activeStream.streaming}
                    hasText={false}
                    onCancel={() => stream.cancel(session.id)}
                  />
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
            <Command className="size-5" />
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
              title={
                activeStream.streaming
                  ? "응답 완료 후 자동 전송"
                  : "Send message"
              }
              disabled={!sendable}
              onClick={handleSend}
              className="rounded-full bg-primary p-2 text-primary-foreground disabled:opacity-50"
            >
              <ArrowUp className="size-5" />
            </button>
          ) : (
            <button
              type="button"
              aria-label="Start voice mode"
              onClick={handleVoiceOpen}
              className="rounded-full p-2 text-muted-foreground transition-colors hover:bg-muted"
              title="음성 모드"
            >
              <Mic className="size-5" />
            </button>
          )}
        </div>
      </footer>

      {/* Sessions slide-in (hamburger → left). Pushes the chat aside
          so the user can pick another chat without losing the
          current one's place. Tapping the backdrop or a session row
          closes the drawer; if a different chat is selected we
          navigate there. */}
      <SlideDrawer
        side="left"
        open={sessionsOpen}
        onClose={() => setSessionsOpen(false)}
        backdropLabel="Close sessions"
      >
        <SessionsDrawerPanel
          activeBot={session.bot}
          activeSessionId={session.id}
          onSelect={(target) => {
            setSessionsOpen(false);
            if (target.bot !== session.bot || target.id !== session.id) {
              router.push(`/mobile/chat/${target.bot}/${target.id}`);
            }
          }}
          onCreate={(botName, newSessionId) => {
            setSessionsOpen(false);
            router.push(`/mobile/chat/${botName}/${newSessionId}`);
          }}
        />
      </SlideDrawer>

      {/* Workspace slide-in. Pushes the chat aside (transform-based)
          instead of stacking a centred modal — the user explicitly
          asked for the "drawer pushes the chat" pattern.
          ``WorkspaceTree`` already renders its own header + Finder /
          Refresh / Close, so the drawer chrome stays minimal. */}
      <SlideDrawer
        side="right"
        open={workspaceOpen}
        onClose={() => setWorkspaceOpen(false)}
        backdropLabel="Close workspace"
        className="w-[90vw] max-w-md"
      >
        <div className="flex-1 overflow-hidden">
          <WorkspaceTree
            bot={session.bot}
            sessionId={session.id}
            onClose={() => setWorkspaceOpen(false)}
          />
        </div>
      </SlideDrawer>

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

      {/* Voice mode — full-screen Orb overlay. Mirrors the desktop
          right-sidebar pattern (removed in c983c9b) on mobile. The
          ``fixed inset-0 z-[60]`` covers everything except slide
          drawers (which we force-close on open). */}
      {voiceMode && (
        <div className="fixed inset-0 z-[60] bg-background">
          <VoiceScreen
            botDisplayName={botSummary.display_name}
            voiceState={voice.voiceState}
            partialTranscript={voice.partialTranscript}
            error={voice.error}
            onClose={handleVoiceClose}
          />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pieces
// ---------------------------------------------------------------------------

/**
 * In-flight reply indicator — three bouncing dots + adaptive elapsed time.
 *
 * UX rules:
 *   - Dots bounce in sequence regardless of elapsed time (always alive).
 *   - The "Ns" counter stays hidden for the first 3s so fast responses
 *     don't flash a stale number.
 *   - After 30s, the label changes to "Still thinking · Ns" so the user
 *     knows a long task is still progressing instead of silently stuck.
 *
 * The counter refreshes every 500ms (the cheap path) to keep the
 * sub-second feel without burning re-renders.
 */
function StreamingDots({ inline = false }: { inline?: boolean }) {
  return (
    <span
      role="presentation"
      aria-hidden
      className={inline ? "inline-flex items-center gap-1" : "flex items-center gap-1"}
    >
      <span
        className="block h-1.5 w-1.5 rounded-full bg-current"
        style={{ animation: "stream-dot 1.2s ease-in-out infinite", animationDelay: "0ms" }}
      />
      <span
        className="block h-1.5 w-1.5 rounded-full bg-current"
        style={{ animation: "stream-dot 1.2s ease-in-out infinite", animationDelay: "160ms" }}
      />
      <span
        className="block h-1.5 w-1.5 rounded-full bg-current"
        style={{ animation: "stream-dot 1.2s ease-in-out infinite", animationDelay: "320ms" }}
      />
    </span>
  );
}

/**
 * Inline "✕" cancel button. Visually small (20 px) but a 44 px tap
 * region is provided via ``-m-3 p-3`` to meet the Apple HIG touch
 * target without bloating the layout.
 */
function CancelStreamButton({ onCancel }: { onCancel: () => void }) {
  return (
    <button
      type="button"
      onClick={onCancel}
      aria-label="Stop generating reply"
      className="-m-3 inline-flex items-center justify-center rounded-full p-3 text-muted-foreground transition-colors hover:text-foreground active:text-foreground"
    >
      <span className="flex h-5 w-5 items-center justify-center rounded-full border border-current">
        <X className="h-3 w-3" aria-hidden />
      </span>
    </button>
  );
}

/**
 * Detect touch-only input devices via the standard CSS media query.
 *
 * ``(hover: none) and (pointer: coarse)`` matches phones / tablets but
 * not a laptop with a touchscreen + keyboard (which reports
 * ``hover: hover``). The result starts ``false`` so SSR stays
 * deterministic; the actual value lands on first paint via the
 * ``useEffect`` below. ``addEventListener('change', ...)`` keeps the
 * value live if the user docks an external keyboard mid-session.
 */
function useIsTouchDevice() {
  const [isTouch, setIsTouch] = React.useState(false);
  React.useEffect(() => {
    const query = window.matchMedia("(hover: none) and (pointer: coarse)");
    const update = () => setIsTouch(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return isTouch;
}

function StreamProgress({
  streaming,
  hasText,
  onCancel,
}: {
  streaming: boolean;
  hasText: boolean;
  onCancel?: () => void;
}) {
  const [elapsed, setElapsed] = React.useState(0);
  React.useEffect(() => {
    if (!streaming) {
      setElapsed(0);
      return;
    }
    const startedAt = Date.now();
    setElapsed(0);
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 500);
    return () => clearInterval(id);
  }, [streaming]);

  if (!streaming) return null;

  // Empty bubble — dots carry the whole indicator and serve as the
  // placeholder for "reply on the way".
  if (!hasText) {
    const showLong = elapsed >= 30;
    return (
      <div className="flex items-center gap-2 py-0.5 text-muted-foreground">
        <StreamingDots inline />
        {showLong && (
          <span className="tabular-nums text-[11px]">Still thinking · {elapsed}s</span>
        )}
        {onCancel && <CancelStreamButton onCancel={onCancel} />}
      </div>
    );
  }

  // Streaming text is already rendering — show a subtle bottom-row
  // indicator that fades the counter in after a few seconds.
  const showElapsed = elapsed >= 3;
  const longRunning = elapsed >= 30;
  return (
    <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
      <StreamingDots inline />
      <span
        className={`tabular-nums transition-opacity duration-300 ${
          showElapsed ? "opacity-100" : "opacity-0"
        }`}
      >
        {longRunning ? `Still thinking · ${elapsed}s` : `${elapsed}s`}
      </span>
      {onCancel && <CancelStreamButton onCancel={onCancel} />}
    </div>
  );
}

function MessageBubble({
  message,
  queued = false,
  onCancelQueue,
}: {
  message: ConversationMessage;
  queued?: boolean;
  onCancelQueue?: () => void;
}) {
  const isUser = message.role === "user";
  return (
    <li className={`flex min-w-0 ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`flex max-w-[85%] flex-col gap-1 ${
          isUser ? "items-end" : "items-start"
        }`}
      >
        <div
          className={`min-w-0 overflow-hidden rounded-2xl px-3 py-2 text-sm ${
            isUser
              ? `bg-primary text-primary-foreground ${queued ? "opacity-70" : ""}`
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
        {queued && (
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
            <StreamingDots inline />
            <span>응답 완료 후 전송</span>
            {onCancelQueue && (
              <button
                type="button"
                onClick={onCancelQueue}
                aria-label="Cancel queued message"
                className="-m-2 inline-flex items-center justify-center rounded-full p-2 hover:text-foreground"
              >
                <span className="flex h-4 w-4 items-center justify-center rounded-full border border-current">
                  <X className="h-2.5 w-2.5" aria-hidden />
                </span>
              </button>
            )}
          </div>
        )}
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
const MarkdownBody = React.memo(function MarkdownBody({
  content,
}: {
  content: string;
}) {
  // ``min-w-0`` lets this flex/grid child actually shrink below its
  // content's intrinsic width. ``break-words`` +
  // ``[overflow-wrap:anywhere]`` break long unbreakable strings
  // (URLs, Korean blobs without spaces) instead of pushing the
  // bubble wider. ``<pre>`` blocks get their own ``overflow-x-auto``
  // so a wide code line scrolls within the bubble — never the
  // whole page. Tables get the same treatment.
  return (
    <div className="prose prose-sm dark:prose-invert min-w-0 max-w-full break-words [overflow-wrap:anywhere] text-foreground prose-headings:text-foreground prose-p:text-foreground prose-strong:text-foreground prose-em:text-foreground prose-li:text-foreground prose-blockquote:text-foreground prose-code:text-foreground prose-a:text-foreground prose-pre:my-2 prose-pre:max-w-full prose-pre:overflow-x-auto prose-pre:rounded-md prose-pre:bg-background/40 prose-pre:p-2 prose-code:break-words prose-img:max-w-full prose-table:block prose-table:max-w-full prose-table:overflow-x-auto prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1 prose-li:my-0">
      {/* ``remarkBreaks`` turns single ``\n`` into ``<br>`` — without
          it CommonMark collapses single newlines to a space, which
          made schedule bullets and short status replies render as
          one giant run-on paragraph on the phone. ``remarkGfm`` adds
          tables / strikethrough / autolinks so assistant replies
          render the same as on GitHub. */}
      <ReactMarkdown remarkPlugins={[remarkBreaks, remarkGfm]}>
        {content || ""}
      </ReactMarkdown>
    </div>
  );
});

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

