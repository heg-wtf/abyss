"use client";

import * as React from "react";
import { Check, Copy, X } from "lucide-react";
import { MarkdownBody } from "./mobile-chat-markdown-body";
import { StreamingDots } from "./mobile-chat-streaming";
import { formatTime } from "./mobile-chat-helpers";
import type { ConversationMessage } from "./mobile-chat-types";
import type { FeedbackSignal } from "@/lib/abyss-api";

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
      // Goes through the Next.js proxy so the request lands on the
      // same origin the PWA was served from. The browser cannot
      // reach the Python sidecar (127.0.0.1:3848) directly when the
      // PWA is opened from a phone via Tailscale — the phone's own
      // loopback has no sidecar — so calling the absolute URL from
      // ``postFeedback`` would only emit a CORS preflight and never
      // a real POST.
      const response = await fetch(
        `/api/chat/sessions/${encodeURIComponent(bot)}/${encodeURIComponent(sessionId)}/feedback`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ turn_id: turnId, signal }),
        },
      );
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
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
    <>
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
    </>
  );
}

function CopyButton({ content }: { content: string }) {
  const [copied, setCopied] = React.useState(false);
  const timerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  React.useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const handleCopy = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(content);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = content;
        textarea.setAttribute("readonly", "");
        textarea.style.position = "absolute";
        textarea.style.left = "-9999px";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      setCopied(true);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard unavailable — ignore
    }
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={copied ? "복사됨" : "메시지 복사"}
      title={copied ? "복사됨" : "복사"}
      className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-border bg-background text-muted-foreground transition-colors hover:bg-muted"
    >
      {copied ? (
        <Check className="h-3.5 w-3.5" aria-hidden />
      ) : (
        <Copy className="h-3.5 w-3.5" aria-hidden />
      )}
    </button>
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
  const showCopy = !message.streaming && !!message.content;
  const showFeedback =
    !isUser &&
    !message.streaming &&
    !!message.content &&
    !!message.timestamp &&
    !!bot &&
    !!sessionId;
  const showActions = showCopy || showFeedback;
  return (
    <li className={`flex min-w-0 ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`flex max-w-[85%] flex-col gap-1 ${
          isUser ? "items-end" : "items-start"
        }`}
      >
        <div
          className={`min-w-0 overflow-hidden rounded-2xl px-3 py-2 text-base leading-relaxed ${
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
            {message.attachments.map((att) =>
              att.mime?.startsWith("image/") ? (
                // Image attachments render as an inline thumbnail so a
                // sent screenshot is recognisable at a glance instead of
                // showing only its filename. Tapping opens the full image.
                <a
                  key={att.real_name}
                  href={att.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block overflow-hidden rounded-md border bg-background/30"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={att.url}
                    alt={att.display_name}
                    loading="lazy"
                    className="max-h-40 w-auto max-w-full object-contain"
                  />
                </a>
              ) : (
                <a
                  key={att.real_name}
                  href={att.url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-md border bg-background/30 px-2 py-1 text-xs text-current underline-offset-2 hover:underline"
                >
                  📎 {att.display_name}
                </a>
              ),
            )}
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
        {showActions ? (
          <div className="mt-1 flex items-center gap-1.5">
            {showCopy ? <CopyButton content={message.content} /> : null}
            {showFeedback ? (
              <FeedbackButtons
                bot={bot!}
                sessionId={sessionId!}
                turnId={message.timestamp}
              />
            ) : null}
          </div>
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
