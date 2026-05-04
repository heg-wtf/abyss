"use client";

import * as React from "react";
import { AlertCircle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  cancelChat,
  type BotSummary,
  type ChatMessage as ChatMessageType,
  type ChatSession,
  type UploadedAttachment,
} from "@/lib/abyss-api";
import { BotSelector } from "./bot-selector";
import { ChatMessage } from "./chat-message";
import { ChatSessionList } from "./chat-session-list";
import { PromptInput } from "./prompt-input";
import { useChatStream } from "./use-chat-stream";

interface ConversationMessage extends ChatMessageType {
  id: string;
  streaming?: boolean;
}

interface Props {
  initialBots: BotSummary[];
  apiOnline: boolean;
}

const newId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

export function ChatView({ initialBots, apiOnline }: Props) {
  const [bots] = React.useState<BotSummary[]>(initialBots);
  const [sessions, setSessions] = React.useState<ChatSession[]>([]);
  const [activeSession, setActiveSession] = React.useState<ChatSession | null>(null);
  const [activeBot, setActiveBot] = React.useState<string | null>(
    initialBots[0]?.name ?? null
  );
  const [messages, setMessages] = React.useState<ConversationMessage[]>([]);
  const [sessionsLoading, setSessionsLoading] = React.useState(false);
  const [messagesLoading, setMessagesLoading] = React.useState(false);
  const [transientError, setTransientError] = React.useState<string | null>(null);

  const stream = useChatStream();
  const scrollRegionRef = React.useRef<HTMLDivElement>(null);

  // Refresh session lists for all bots
  const reloadAllSessions = React.useCallback(async () => {
    if (!apiOnline || bots.length === 0) return;
    setSessionsLoading(true);
    try {
      const all: ChatSession[] = [];
      for (const bot of bots) {
        const response = await fetch(
          `/api/chat/sessions?bot=${encodeURIComponent(bot.name)}`
        );
        if (response.ok) {
          const data = (await response.json()) as { sessions: ChatSession[] };
          all.push(...data.sessions);
        }
      }
      all.sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1));
      setSessions(all);
    } finally {
      setSessionsLoading(false);
    }
  }, [apiOnline, bots]);

  React.useEffect(() => {
    void reloadAllSessions();
  }, [reloadAllSessions]);

  // Load messages whenever the active session changes
  React.useEffect(() => {
    if (!activeSession) {
      setMessages([]);
      return;
    }
    setMessagesLoading(true);
    fetch(
      `/api/chat/sessions/${encodeURIComponent(activeSession.bot)}/${encodeURIComponent(activeSession.id)}/messages`
    )
      .then((response) => (response.ok ? response.json() : { messages: [] }))
      .then((data: { messages: ChatMessageType[] }) => {
        setMessages(
          data.messages.map((message) => ({ ...message, id: newId() }))
        );
      })
      .finally(() => setMessagesLoading(false));
  }, [activeSession]);

  // Auto-scroll to bottom on new content
  React.useEffect(() => {
    const region = scrollRegionRef.current;
    if (!region) return;
    region.scrollTop = region.scrollHeight;
  }, [messages, stream.text]);

  const handleNewChat = async () => {
    if (!activeBot) {
      setTransientError("Select a bot first");
      return;
    }
    const response = await fetch("/api/chat/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bot: activeBot }),
    });
    if (!response.ok) {
      setTransientError(`Failed to create session: ${response.status}`);
      return;
    }
    const session = (await response.json()) as ChatSession;
    setSessions((prev) => [session, ...prev]);
    setActiveSession(session);
    setMessages([]);
  };

  const handleDelete = async (session: ChatSession) => {
    const label = session.bot_display_name || session.bot;
    if (!confirm(`Delete chat with ${label}?`)) return;
    await fetch(
      `/api/chat/sessions/${encodeURIComponent(session.bot)}/${encodeURIComponent(session.id)}`,
      { method: "DELETE" }
    );
    setSessions((prev) => prev.filter((current) => current.id !== session.id));
    if (activeSession?.id === session.id) {
      setActiveSession(null);
      setMessages([]);
    }
  };

  const handleSubmit = async (payload: {
    text: string;
    attachments: UploadedAttachment[];
  }) => {
    if (!activeSession) {
      setTransientError("Pick or create a chat first");
      return;
    }
    const session = activeSession;
    const optimisticAttachments = payload.attachments.map((attachment) => {
      const realName = attachment.path.startsWith("uploads/")
        ? attachment.path.slice("uploads/".length)
        : attachment.path;
      return {
        display_name: attachment.display_name,
        real_name: realName,
        mime: attachment.mime,
        url: `/api/chat/sessions/${encodeURIComponent(session.bot)}/${encodeURIComponent(session.id)}/file/${encodeURIComponent(realName)}`,
      };
    });

    const userMessage: ConversationMessage = {
      id: newId(),
      role: "user",
      content: payload.text,
      timestamp: new Date().toISOString(),
      attachments:
        optimisticAttachments.length > 0 ? optimisticAttachments : undefined,
    };
    const assistantId = newId();
    setMessages((prev) => [
      ...prev,
      userMessage,
      {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date().toISOString(),
        streaming: true,
      },
    ]);
    setTransientError(null);

    const final = await stream.send(
      session.bot,
      session.id,
      payload.text,
      payload.attachments.map((attachment) => attachment.path)
    );
    setMessages((prev) =>
      prev.map((message) =>
        message.id === assistantId
          ? { ...message, content: final, streaming: false }
          : message
      )
    );
    void reloadAllSessions();
  };

  const handleCancel = async () => {
    stream.cancel();
    if (activeSession) {
      await cancelChat(activeSession.bot, activeSession.id).catch(() => {
        /* ignore */
      });
    }
  };

  // Reflect streaming text into the in-flight assistant message
  React.useEffect(() => {
    if (!stream.streaming) return;
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (!last || last.role !== "assistant") return prev;
      if (last.content === stream.text) return prev;
      const next = prev.slice();
      next[next.length - 1] = { ...last, content: stream.text };
      return next;
    });
  }, [stream.text, stream.streaming]);

  if (!apiOnline) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <Alert variant="destructive" className="max-w-md">
          <AlertCircle className="size-4" />
          <AlertTitle>Chat server is not running</AlertTitle>
          <AlertDescription>
            Run <code className="font-mono">abyss start</code> to launch the bots and the chat
            server. Once it&apos;s running, refresh this page.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      <ChatSessionList
        sessions={sessions}
        activeId={activeSession?.id ?? null}
        loading={sessionsLoading}
        onSelect={(session) => {
          setActiveBot(session.bot);
          setActiveSession(session);
        }}
        onCreate={handleNewChat}
        onDelete={handleDelete}
      />
      <main className="flex min-h-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b bg-background px-4 py-2">
          <div className="flex items-center gap-3">
            <BotSelector
              bots={bots}
              value={activeBot}
              onChange={setActiveBot}
              disabled={!!activeSession}
            />
            {activeSession && (
              <span className="text-xs text-muted-foreground">
                Session <code>{activeSession.id}</code>
              </span>
            )}
          </div>
          {!activeSession && activeBot && (
            <Button size="sm" onClick={handleNewChat}>
              Start chat
            </Button>
          )}
        </header>
        {transientError && (
          <div className="bg-destructive/10 px-4 py-2 text-sm text-destructive">
            {transientError}
          </div>
        )}
        {stream.error && (
          <div className="bg-destructive/10 px-4 py-2 text-sm text-destructive">
            {stream.error}
          </div>
        )}
        <ScrollArea className="min-h-0 flex-1">
          <div ref={scrollRegionRef} className="flex min-h-full flex-col">
            {messagesLoading && (
              <div className="px-4 py-3 text-sm text-muted-foreground">Loading…</div>
            )}
            {!messagesLoading && messages.length === 0 && (
              <div className="flex flex-1 items-center justify-center px-4 text-center text-sm text-muted-foreground">
                {activeSession
                  ? "Send a message to start the conversation."
                  : "Pick a chat from the left or start a new one."}
              </div>
            )}
            {messages.map((message) => (
              <ChatMessage
                key={message.id}
                role={message.role}
                content={message.content}
                streaming={message.streaming && stream.streaming}
                botName={activeSession?.bot ?? null}
                botDisplayName={
                  activeSession?.bot_display_name ?? activeSession?.bot ?? null
                }
                attachments={message.attachments}
              />
            ))}
          </div>
        </ScrollArea>
        <PromptInput
          bot={activeSession?.bot ?? null}
          sessionId={activeSession?.id ?? null}
          onSubmit={handleSubmit}
          onCancel={handleCancel}
          streaming={stream.streaming}
          disabled={!activeSession || stream.streaming}
          placeholder={
            activeSession
              ? `Message ${activeSession.bot_display_name || activeSession.bot}…`
              : activeBot
                ? "Click 'Start chat' to begin"
                : "Pick a bot first"
          }
        />
      </main>
    </div>
  );
}
