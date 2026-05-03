"use client";

import * as React from "react";
import ReactMarkdown from "react-markdown";
import { Bot, User } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

export function ChatMessage({ role, content, streaming }: Props) {
  const isUser = role === "user";
  return (
    <div className={cn("flex gap-3 px-4 py-3", isUser && "bg-muted/30")}>
      <div className="mt-1">
        {isUser ? (
          <User className="size-5 text-muted-foreground" />
        ) : (
          <Bot className="size-5 text-primary" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="mb-1 text-xs font-medium text-muted-foreground">
          {isUser ? "You" : "Bot"}
          {streaming && (
            <span className="ml-2 inline-block animate-pulse">●</span>
          )}
        </div>
        <div className="prose prose-sm dark:prose-invert max-w-none break-words">
          {role === "assistant" ? (
            <ReactMarkdown>{content || (streaming ? "…" : "")}</ReactMarkdown>
          ) : (
            <div className="whitespace-pre-wrap">{content}</div>
          )}
        </div>
      </div>
    </div>
  );
}
