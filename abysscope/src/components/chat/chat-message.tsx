"use client";

import * as React from "react";
import ReactMarkdown from "react-markdown";
import { FileText, User } from "lucide-react";
import { BotAvatar } from "@/components/bot-avatar";
import { cn } from "@/lib/utils";
import type { ChatAttachmentRef } from "@/lib/abyss-api";

interface Props {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  botName?: string | null;
  botDisplayName?: string | null;
  attachments?: ChatAttachmentRef[];
  timestamp?: string | null;
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  if (isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("ko-KR", { hour: "numeric", minute: "2-digit", hour12: true });
}

export function ChatMessage({
  role,
  content,
  streaming,
  botName,
  botDisplayName,
  attachments,
  timestamp,
}: Props) {
  const isUser = role === "user";
  const displayName = botDisplayName || botName || "Bot";
  const timeLabel = !streaming && timestamp ? formatTime(timestamp) : null;
  return (
    <div
      className={cn(
        "flex gap-3 border-b px-4 py-3 last:border-b-0",
        isUser && "bg-muted/30",
      )}
    >
      <div className="mt-1">
        {isUser ? (
          <User className="size-5 text-muted-foreground" />
        ) : (
          <BotAvatar
            botName={botName ?? ""}
            displayName={displayName}
            size="xs"
          />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="mb-1 flex items-baseline gap-2 text-xs font-medium text-muted-foreground">
          <span>{isUser ? "You" : displayName}</span>
          {streaming && (
            <span className="inline-block animate-pulse">●</span>
          )}
          {timeLabel && <span className="font-normal">{timeLabel}</span>}
        </div>
        {attachments && attachments.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {attachments.map((attachment) => (
              <AttachmentTile key={attachment.url} attachment={attachment} />
            ))}
          </div>
        )}
        <div className="prose prose-sm dark:prose-invert min-w-0 max-w-none break-words [overflow-wrap:anywhere]">
          {role === "assistant" ? (
            <ReactMarkdown>{content || (streaming ? "…" : "")}</ReactMarkdown>
          ) : content ? (
            <div className="whitespace-pre-wrap">{content}</div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function AttachmentTile({ attachment }: { attachment: ChatAttachmentRef }) {
  const isImage = attachment.mime.startsWith("image/");
  return (
    <a
      href={attachment.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex items-center gap-2 rounded-md border bg-background px-2 py-1 text-xs hover:bg-muted"
      title={attachment.display_name}
    >
      {isImage ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={attachment.url}
          alt={attachment.display_name}
          className="size-12 rounded object-cover"
          loading="lazy"
        />
      ) : (
        <FileText className="size-5 text-muted-foreground" />
      )}
      <span className="max-w-[160px] truncate">{attachment.display_name}</span>
    </a>
  );
}
