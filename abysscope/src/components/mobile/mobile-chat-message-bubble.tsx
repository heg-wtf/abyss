"use client";

import * as React from "react";
import { X } from "lucide-react";
import { MarkdownBody } from "./mobile-chat-markdown-body";
import { StreamingDots } from "./mobile-chat-streaming";
import { formatTime } from "./mobile-chat-helpers";
import type { ConversationMessage } from "./mobile-chat-types";

export function MessageBubble({
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
