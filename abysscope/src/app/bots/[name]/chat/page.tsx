"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

interface Message {
  role: "user" | "assistant";
  content: string;
  source: "telegram" | "dashboard";
  timestamp?: string;
}

export default function ChatPage() {
  const { name } = useParams<{ name: string }>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamBuffer, setStreamBuffer] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Load history on mount
  useEffect(() => {
    fetch(`/api/bots/${name}/chat?history=1`)
      .then((r) => r.json())
      .then((data) => {
        const history: string = data.history || "";
        if (history) {
          const parsed = parseMarkdownHistory(history);
          setMessages(parsed);
        }
      })
      .catch(() => {});
  }, [name]);

  // Subscribe to real-time Telegram events
  useEffect(() => {
    const es = new EventSource(`/api/bots/${name}/chat`);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "message") {
          setMessages((prev) => [
            ...prev,
            {
              role: data.role,
              content: data.content,
              source: data.source,
              timestamp: data.timestamp,
            },
          ]);
        }
      } catch {
        // ignore malformed events
      }
    };

    return () => {
      es.close();
    };
  }, [name]);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamBuffer]);

  async function sendMessage() {
    const text = input.trim();
    if (!text || streaming) return;

    setInput("");
    setStreaming(true);
    setStreamBuffer("");

    const userMsg: Message = {
      role: "user",
      content: text,
      source: "dashboard",
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const response = await fetch(`/api/bots/${name}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });

      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";
      let lineBuffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        lineBuffer += decoder.decode(value, { stream: true });
        const lines = lineBuffer.split("\n");
        // Retain potentially incomplete last line for the next read
        lineBuffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === "chunk") {
              accumulated += data.content;
              setStreamBuffer(accumulated);
            } else if (data.type === "done") {
              setMessages((prev) => [
                ...prev,
                {
                  role: "assistant",
                  content: data.content || accumulated,
                  source: "dashboard",
                },
              ]);
              setStreamBuffer("");
              accumulated = "";
            }
          } catch {
            // ignore parse errors for incomplete lines
          }
        }
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${err}`,
          source: "dashboard",
        },
      ]);
      setStreamBuffer("");
    } finally {
      setStreaming(false);
      inputRef.current?.focus();
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem-3rem)]">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4 flex-shrink-0">
        <Link href="/" className="text-muted-foreground hover:text-foreground text-sm">
          Dashboard
        </Link>
        <span className="text-muted-foreground">/</span>
        <Link
          href={`/bots/${name}`}
          className="text-muted-foreground hover:text-foreground text-sm"
        >
          {name}
        </Link>
        <span className="text-muted-foreground">/</span>
        <h1 className="text-2xl font-bold">Chat</h1>
        <span className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="w-2 h-2 rounded-full bg-green-500 inline-block" />
          Live
        </span>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}

        {/* Streaming buffer */}
        {streamBuffer && (
          <MessageBubble
            message={{ role: "assistant", content: streamBuffer, source: "dashboard" }}
            isStreaming
          />
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex-shrink-0 border-t pt-4">
        <div className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={streaming}
            rows={2}
            placeholder="Message... (Enter to send, Shift+Enter for newline)"
            className="flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || streaming}
            className="rounded-md bg-primary text-primary-foreground px-4 py-2 text-sm font-medium hover:bg-primary/90 disabled:opacity-50 h-[4.5rem]"
          >
            {streaming ? "..." : "Send"}
          </button>
        </div>
        <p className="text-xs text-muted-foreground mt-1.5">
          Messages sync bidirectionally with Telegram.
        </p>
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  isStreaming,
}: {
  message: Message;
  isStreaming?: boolean;
}) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap break-words ${
          isUser
            ? "bg-primary text-primary-foreground rounded-br-sm"
            : "bg-muted rounded-bl-sm"
        } ${isStreaming ? "opacity-70" : ""}`}
      >
        {message.content}
        {isStreaming && <span className="animate-pulse ml-0.5">▊</span>}
        {message.source === "telegram" && (
          <div className="text-[10px] opacity-60 mt-1">via Telegram</div>
        )}
      </div>
    </div>
  );
}

function parseMarkdownHistory(markdown: string): Message[] {
  const messages: Message[] = [];
  const lines = markdown.split("\n");

  let currentRole: "user" | "assistant" | null = null;
  let currentLines: string[] = [];

  function flush() {
    if (currentRole && currentLines.length > 0) {
      const content = currentLines.join("\n").trim();
      if (content) {
        messages.push({ role: currentRole, content, source: "telegram" });
      }
    }
    currentLines = [];
  }

  // Format written by session.log_conversation: "## user (timestamp)" / "## assistant (timestamp)"
  for (const line of lines) {
    if (/^## user\b/.test(line)) {
      flush();
      currentRole = "user";
    } else if (/^## assistant\b/.test(line)) {
      flush();
      currentRole = "assistant";
    } else if (currentRole) {
      currentLines.push(line);
    }
  }
  flush();
  return messages;
}
