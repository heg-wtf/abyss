"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import {
  ArrowUp,
  Clock,
  HeartPulse,
  Menu as MenuIcon,
  RefreshCw,
} from "lucide-react";
import { BotAvatar } from "@/components/bot-avatar";
import { SlideDrawer } from "@/components/mobile/slide-drawer";
import { SessionsDrawerPanel } from "@/components/mobile/sessions-drawer-panel";
import { parseChatEvents } from "@/lib/abyss-api";
import type { ChatMessage, RoutineSummary } from "@/lib/abyss-api";

interface Props {
  routine: RoutineSummary;
  initialMessages: ChatMessage[];
}

/**
 * Read-only viewer for a single cron / heartbeat routine.
 *
 * Mirrors ``MobileChatScreen``'s top-bar + message layout so the user
 * does not feel like they've jumped to a different surface, but
 * drops the input bar, slash sheet, voice mode, and workspace drawer
 * — none of those make sense for a scheduled-run history. A refresh
 * button re-fetches via the proxy in case new runs landed while the
 * tab was open.
 */
export function MobileRoutineScreen({ routine, initialMessages }: Props) {
  const router = useRouter();
  const [messages, setMessages] = React.useState<ChatMessage[]>(initialMessages);
  const [refreshing, setRefreshing] = React.useState(false);
  const [sessionsOpen, setSessionsOpen] = React.useState(false);
  const [draft, setDraft] = React.useState("");
  const [sending, setSending] = React.useState(false);

  const refresh = async () => {
    setRefreshing(true);
    try {
      const response = await fetch(
        `/api/chat/routines/${routine.bot}/${routine.kind}/${routine.job_name}/messages`,
      );
      if (!response.ok) return;
      const body = (await response.json()) as { messages: ChatMessage[] };
      setMessages(body.messages ?? []);
    } finally {
      setRefreshing(false);
    }
  };

  const abortRef = React.useRef<AbortController | null>(null);

  // Cancel any in-flight reply on unmount so a setMessages on a dead
  // component (and the orphan optimistic bubble) never happens.
  React.useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

  const send = async () => {
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);

    // Optimistic user bubble so the input feels responsive while the
    // SSE response streams in. Rolled back below if the request
    // fails or is aborted before the assistant reply lands.
    const optimistic: ChatMessage = {
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);
    setDraft("");

    const controller = new AbortController();
    abortRef.current = controller;

    let assistantText = "";
    try {
      const response = await fetch(
        `/api/chat/routines/${routine.bot}/${routine.kind}/${routine.job_name}/chat`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
          signal: controller.signal,
        },
      );
      if (!response.ok || !response.body) {
        setMessages((prev) => prev.filter((m) => m !== optimistic));
        return;
      }
      for await (const event of parseChatEvents(response.body)) {
        if (event.type === "chunk") {
          assistantText += event.text;
        } else if (event.type === "done") {
          assistantText = event.text;
        }
      }
      if (assistantText) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: assistantText,
            timestamp: new Date().toISOString(),
          },
        ]);
      }
    } catch (error) {
      if ((error as Error)?.name !== "AbortError") {
        // Stream errored before the assistant reply landed —
        // drop the optimistic bubble so the user can retry without
        // a ghost message in the transcript.
        setMessages((prev) => prev.filter((m) => m !== optimistic));
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setSending(false);
    }
  };

  const Icon = routine.kind === "cron" ? Clock : HeartPulse;

  return (
    <div className="flex h-full min-w-0 flex-col overflow-x-hidden">
      <header className="flex h-14 shrink-0 items-center gap-2 border-b px-3">
        <button
          type="button"
          aria-label="Open sessions"
          onClick={() => setSessionsOpen(true)}
          className="rounded-full p-2 text-muted-foreground hover:bg-muted"
        >
          <MenuIcon className="size-5" />
        </button>
        <BotAvatar
          botName={routine.bot}
          displayName={routine.bot_display_name}
          size="sm"
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 truncate text-sm font-medium">
            <Icon className="size-3.5 shrink-0 text-muted-foreground" />
            <span className="truncate">{routine.job_name}</span>
          </div>
          <div className="truncate text-xs text-muted-foreground">
            {routine.bot_display_name} · {routine.kind}
          </div>
        </div>
        <button
          type="button"
          aria-label="Refresh routine messages"
          disabled={refreshing}
          onClick={() => void refresh()}
          className="rounded-full p-2 text-muted-foreground hover:bg-muted disabled:opacity-50"
        >
          <RefreshCw
            className={`size-5 ${refreshing ? "animate-spin" : ""}`}
          />
        </button>
      </header>

      <ul className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto px-3 py-4">
        {messages.length === 0 ? (
          <li className="px-2 py-6 text-center text-sm text-muted-foreground">
            No logged runs yet. This routine will fill in here the
            next time it fires.
          </li>
        ) : (
          messages.map((message, index) => (
            <RoutineMessageBubble
              key={`${index}:${message.timestamp ?? ""}`}
              message={message}
            />
          ))
        )}
      </ul>

      <footer className="shrink-0 border-t bg-background">
        <div className="flex items-end gap-1 px-2 py-2">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing
              ) {
                event.preventDefault();
                void send();
              }
            }}
            placeholder={`${routine.job_name}에게 답하기…`}
            rows={1}
            disabled={sending}
            className="flex-1 resize-none rounded-2xl border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring [&::-webkit-scrollbar]:hidden disabled:opacity-50"
            style={{
              maxHeight: "160px",
              scrollbarWidth: "none",
              msOverflowStyle: "none",
            }}
          />
          <button
            type="button"
            aria-label="Send routine reply"
            disabled={!draft.trim() || sending}
            onClick={() => void send()}
            className="rounded-full bg-primary p-2 text-primary-foreground disabled:opacity-50"
          >
            <ArrowUp className="size-5" />
          </button>
        </div>
      </footer>

      <SlideDrawer
        side="left"
        open={sessionsOpen}
        onClose={() => setSessionsOpen(false)}
        backdropLabel="Close sessions"
      >
        <SessionsDrawerPanel
          activeBot={routine.bot}
          activeSessionId=""
          onSelect={(target) => {
            setSessionsOpen(false);
            router.push(`/mobile/chat/${target.bot}/${target.id}`);
          }}
          onCreate={(botName, newSessionId) => {
            setSessionsOpen(false);
            router.push(`/mobile/chat/${botName}/${newSessionId}`);
          }}
        />
      </SlideDrawer>

    </div>
  );
}

const RoutineMessageBubble = React.memo(function RoutineMessageBubble({
  message,
}: {
  message: ChatMessage;
}) {
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
          <div className="whitespace-pre-wrap text-xs opacity-80">
            {/* The "user" side of a routine is the trigger prompt
                rather than something the human typed. Render it
                muted so the run output (assistant side) reads as the
                main signal. */}
            {message.content}
          </div>
        ) : (
          <div className="prose prose-sm dark:prose-invert min-w-0 max-w-full break-words [overflow-wrap:anywhere] text-foreground prose-headings:text-foreground prose-p:text-foreground prose-strong:text-foreground prose-em:text-foreground prose-li:text-foreground prose-blockquote:text-foreground prose-code:text-foreground prose-a:text-foreground prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1 prose-li:my-0">
            <ReactMarkdown remarkPlugins={[remarkBreaks, remarkGfm]}>
              {message.content || ""}
            </ReactMarkdown>
          </div>
        )}
        {message.timestamp && (
          <div className="mt-1 text-right text-[10px] opacity-60">
            {new Date(message.timestamp).toLocaleString("ko-KR", {
              month: "numeric",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </div>
        )}
      </div>
    </li>
  );
});
