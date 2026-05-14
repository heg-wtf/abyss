"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import { ArrowLeft, Clock, HeartPulse, RefreshCw } from "lucide-react";
import { BotAvatar } from "@/components/bot-avatar";
import { SlideDrawer } from "@/components/mobile/slide-drawer";
import { SessionsDrawerPanel } from "@/components/mobile/sessions-drawer-panel";
import type {
  BotSummary,
  ChatMessage,
  RoutineSummary,
} from "@/lib/abyss-api";

interface Props {
  bots: BotSummary[];
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
export function MobileRoutineScreen({ bots, routine, initialMessages }: Props) {
  const router = useRouter();
  const [messages, setMessages] = React.useState<ChatMessage[]>(initialMessages);
  const [refreshing, setRefreshing] = React.useState(false);
  const [sessionsOpen, setSessionsOpen] = React.useState(false);

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

  const Icon = routine.kind === "cron" ? Clock : HeartPulse;

  return (
    <div className="flex h-full min-w-0 flex-col overflow-x-hidden">
      <header className="flex h-14 shrink-0 items-center gap-2 border-b px-3">
        <button
          type="button"
          aria-label="Back to chats"
          onClick={() => router.push("/mobile")}
          className="rounded-full p-2 text-muted-foreground hover:bg-muted"
        >
          <ArrowLeft className="size-5" />
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

      {/* ``bots`` is unused inside the routine screen today, but
          stays threaded through the page so future "switch routine"
          affordances can pick from the same roster the chat surface
          uses. */}
      <span className="hidden">{bots.length}</span>
    </div>
  );
}

function RoutineMessageBubble({ message }: { message: ChatMessage }) {
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
}
