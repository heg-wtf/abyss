"use client";

import * as React from "react";
import { X } from "lucide-react";
import { MarkdownBody } from "./mobile-chat-markdown-body";
import { StreamingDots } from "./mobile-chat-streaming";
import { formatTime } from "./mobile-chat-helpers";
import type { ConversationMessage } from "./mobile-chat-types";
import {
  postFeedback,
  type FeedbackSignal,
} from "@/lib/abyss-api";

const SIGNAL_LABELS: Record<FeedbackSignal, string> = {
  1: "좋음",
  2: "별로",
  3: "틀림",
};

function feedbackStorageKey(
  bot: string,
  sessionId: string,
  turnId: string,
): string {
  return `feedback:${bot}:${sessionId}:${turnId}`;
}

function FeedbackButtons({
  bot,
  sessionId,
  turnId,
}: {
  bot: string;
  sessionId: string;
  turnId: string;
}) {
  const storageKey = React.useMemo(
    () => feedbackStorageKey(bot, sessionId, turnId),
    [bot, sessionId, turnId],
  );

  const [selected, setSelected] = React.useState<FeedbackSignal | null>(null);
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState(false);

  React.useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const saved = window.localStorage.getItem(storageKey);
      if (saved === "1" || saved === "2" || saved === "3") {
        setSelected(Number(saved) as FeedbackSignal);
      }
    } catch {
      // localStorage unavailable; ignore.
    }
  }, [storageKey]);

  const submit = async (signal: FeedbackSignal) => {
    if (pending) return;
    setPending(true);
    setError(false);
    try {
      await postFeedback(bot, sessionId, turnId, signal);
      setSelected(signal);
      try {
        window.localStorage.setItem(storageKey, String(signal));
      } catch {
        // localStorage quota errors — non-fatal
      }
    } catch {
      setError(true);
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="mt-1 flex items-center gap-1.5">
      {([1, 2, 3] as FeedbackSignal[]).map((value) => {
        const isSelected = selected === value;
        return (
          <button
            key={value}
            type="button"
            onClick={() => submit(value)}
            disabled={pending}
            title={SIGNAL_LABELS[value]}
            aria-label={`피드백 ${value} (${SIGNAL_LABELS[value]})`}
            aria-pressed={isSelected}
            className={`inline-flex h-7 w-7 items-center justify-center rounded-full border text-xs font-medium transition-colors ${
              isSelected
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-background text-muted-foreground hover:bg-muted"
            } ${pending ? "opacity-50" : ""}`}
          >
            {value}
          </button>
        );
      })}
      {error ? (
        <span className="text-[10px] text-destructive">저장 실패</span>
      ) : null}
    </div>
  );
}

export function MessageBubble({
  message,
  queued = false,
  onCancelQueue,
  bot,
  sessionId,
}: {
  message: ConversationMessage;
  queued?: boolean;
  onCancelQueue?: () => void;
  bot?: string;
  sessionId?: string;
}) {
  const isUser = message.role === "user";
  const showFeedback =
    !isUser &&
    !message.streaming &&
    !!message.content &&
    !!message.timestamp &&
    !!bot &&
    !!sessionId;
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
        {showFeedback ? (
          <FeedbackButtons
            bot={bot!}
            sessionId={sessionId!}
            turnId={message.timestamp}
          />
        ) : null}
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
