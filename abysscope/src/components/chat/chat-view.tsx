"use client";

import * as React from "react";
import { AlertCircle, FolderTree, Mic } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { BotAvatar } from "@/components/bot-avatar";
import {
  cancelChat,
  type BotSummary,
  type ChatMessage as ChatMessageType,
  type ChatSession,
  type UploadedAttachment,
} from "@/lib/abyss-api";
import { ChatMessage } from "./chat-message";
import { ChatSessionList } from "./chat-session-list";
import { PromptInput } from "./prompt-input";
import {
  getSessionStream,
  useMultiSessionChatStream,
} from "./use-chat-stream";
import { useVoiceMode, type VoiceState } from "./use-voice-mode";
import { VoiceScreen } from "./voice-screen";
import { WorkspaceTree } from "./workspace-tree";

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
  const [sessionMessages, setSessionMessages] = React.useState<
    Map<string, ConversationMessage[]>
  >(new Map());
  const [loadedSessions, setLoadedSessions] = React.useState<Set<string>>(
    new Set()
  );
  const [sessionsLoading, setSessionsLoading] = React.useState(false);
  const [messagesLoading, setMessagesLoading] = React.useState(false);
  const [transientError, setTransientError] = React.useState<string | null>(null);
  const [voiceMode, setVoiceMode] = React.useState(false);
  const [workspaceOpen, setWorkspaceOpen] = React.useState(false);

  // Track the streaming-assistant message id per session, so chunk reflection
  // can update the correct placeholder even if other messages get appended.
  const streamingMessageIdRef = React.useRef<Map<string, string>>(new Map());

  const stream = useMultiSessionChatStream();
  const bottomRef = React.useRef<HTMLDivElement>(null);

  const activeMessages = React.useMemo<ConversationMessage[]>(() => {
    if (!activeSession) return [];
    return sessionMessages.get(activeSession.id) ?? [];
  }, [activeSession, sessionMessages]);

  const activeStream = getSessionStream(stream.streams, activeSession?.id);

  const updateSessionMessages = React.useCallback(
    (
      sessionId: string,
      updater: (prev: ConversationMessage[]) => ConversationMessage[]
    ) => {
      setSessionMessages((prev) => {
        const next = new Map(prev);
        next.set(sessionId, updater(prev.get(sessionId) ?? []));
        return next;
      });
    },
    []
  );

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

  // Load messages for the active session only when not already loaded.
  // In-flight sessions keep their messages — switching away and back preserves
  // the running stream's accumulated chunks.
  React.useEffect(() => {
    if (!activeSession) return;
    if (loadedSessions.has(activeSession.id)) return;

    setMessagesLoading(true);
    const sessionId = activeSession.id;
    fetch(
      `/api/chat/sessions/${encodeURIComponent(activeSession.bot)}/${encodeURIComponent(sessionId)}/messages`
    )
      .then((response) => (response.ok ? response.json() : { messages: [] }))
      .then((data: { messages: ChatMessageType[] }) => {
        const loaded = data.messages.map((message) => ({
          ...message,
          id: newId(),
        }));
        setSessionMessages((prev) => {
          const next = new Map(prev);
          next.set(sessionId, loaded);
          return next;
        });
        setLoadedSessions((prev) => {
          const next = new Set(prev);
          next.add(sessionId);
          return next;
        });
      })
      .finally(() => setMessagesLoading(false));
  }, [activeSession, loadedSessions]);

  // Auto-scroll to bottom on new content for the active session.
  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [activeMessages, activeStream.text]);

  const handleNewChat = async (botName: string) => {
    if (!botName) {
      setTransientError("Select a bot first");
      return;
    }
    const response = await fetch("/api/chat/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bot: botName }),
    });
    if (!response.ok) {
      setTransientError(`Failed to create session: ${response.status}`);
      return;
    }
    const session = (await response.json()) as ChatSession;
    setSessions((prev) => [session, ...prev]);
    setActiveSession(session);
    setSessionMessages((prev) => {
      const next = new Map(prev);
      next.set(session.id, []);
      return next;
    });
    setLoadedSessions((prev) => {
      const next = new Set(prev);
      next.add(session.id);
      return next;
    });
  };

  const handleDelete = async (session: ChatSession) => {
    const label = session.bot_display_name || session.bot;
    if (!confirm(`Delete chat with ${label}?`)) return;

    // Abort any in-flight stream for this session first.
    stream.cancel(session.id);
    streamingMessageIdRef.current.delete(session.id);

    await fetch(
      `/api/chat/sessions/${encodeURIComponent(session.bot)}/${encodeURIComponent(session.id)}`,
      { method: "DELETE" }
    );

    setSessions((prev) => prev.filter((current) => current.id !== session.id));
    setSessionMessages((prev) => {
      const next = new Map(prev);
      next.delete(session.id);
      return next;
    });
    setLoadedSessions((prev) => {
      const next = new Set(prev);
      next.delete(session.id);
      return next;
    });
    if (activeSession?.id === session.id) {
      setActiveSession(null);
    }
  };

  const handleSubmit = async (payload: {
    text: string;
    attachments: UploadedAttachment[];
    voiceMode?: boolean;
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
    streamingMessageIdRef.current.set(session.id, assistantId);
    updateSessionMessages(session.id, (prev) => [
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
      payload.attachments.map((attachment) => attachment.path),
      payload.voiceMode ?? false
    );

    updateSessionMessages(session.id, (prev) =>
      prev.map((message) =>
        message.id === assistantId
          ? { ...message, content: final, streaming: false }
          : message
      )
    );
    if (streamingMessageIdRef.current.get(session.id) === assistantId) {
      streamingMessageIdRef.current.delete(session.id);
    }
    void reloadAllSessions();
  };

  const handleCancel = async () => {
    if (!activeSession) return;
    stream.cancel(activeSession.id);
    await cancelChat(activeSession.bot, activeSession.id).catch(() => {
      /* ignore */
    });
  };

  const voice = useVoiceMode({
    onTranscript: (text) => {
      void handleSubmit({ text, attachments: [], voiceMode: true });
    },
  });

  // Auto-speak the assistant reply when streaming completes (active session only).
  const prevStreamingRef = React.useRef(false);
  React.useEffect(() => {
    if (!activeSession) {
      prevStreamingRef.current = false;
      return;
    }
    const isStreaming = activeStream.streaming;
    if (prevStreamingRef.current && !isStreaming && voiceMode) {
      const last = activeMessages[activeMessages.length - 1];
      if (last?.role === "assistant" && last.content) {
        void voice.speak(last.content);
      }
    }
    prevStreamingRef.current = isStreaming;
  }, [
    activeStream.streaming,
    activeSession,
    activeMessages,
    voiceMode,
    voice,
  ]);

  // Auto-restart recording after bot finishes speaking.
  const prevVoiceStateRef = React.useRef<VoiceState>("idle");
  React.useEffect(() => {
    const prev = prevVoiceStateRef.current;
    prevVoiceStateRef.current = voice.voiceState;
    if (prev === "speaking" && voice.voiceState === "idle" && voiceMode) {
      void voice.start();
    }
  }, [voice.voiceState, voiceMode, voice]);

  const handleVoiceOpen = () => {
    setWorkspaceOpen(false);
    setVoiceMode(true);
    void voice.start();
  };

  const handleVoiceClose = () => {
    voice.cancel();
    setVoiceMode(false);
  };

  const handleWorkspaceToggle = () => {
    setWorkspaceOpen((prev) => {
      const next = !prev;
      if (next && voiceMode) {
        voice.cancel();
        setVoiceMode(false);
      }
      return next;
    });
  };

  const handleWorkspaceClose = () => {
    setWorkspaceOpen(false);
  };

  // Reflect streaming text into each session's in-flight assistant message.
  // Iterates ALL active streams, not just the active session — so background
  // sessions keep accumulating chunks while the user views another.
  React.useEffect(() => {
    setSessionMessages((prev) => {
      let changed = false;
      const next = new Map(prev);
      for (const [sessionId, sessionStream] of stream.streams) {
        if (!sessionStream.streaming && sessionStream.text === "") continue;
        const assistantId = streamingMessageIdRef.current.get(sessionId);
        if (!assistantId) continue;
        const messages = prev.get(sessionId);
        if (!messages) continue;
        const target = messages.find(
          (message) => message.id === assistantId
        );
        if (!target) continue;
        if (target.content === sessionStream.text) continue;
        next.set(
          sessionId,
          messages.map((message) =>
            message.id === assistantId
              ? { ...message, content: sessionStream.text }
              : message
          )
        );
        changed = true;
      }
      return changed ? next : prev;
    });
  }, [stream.streams]);

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
        bots={bots}
        activeId={activeSession?.id ?? null}
        loading={sessionsLoading}
        onSelect={(session) => setActiveSession(session)}
        onCreate={handleNewChat}
        onDelete={handleDelete}
      />
      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        <>
        <header className="flex h-14 items-center justify-between border-b bg-background px-4">
          <div className="flex items-center gap-3">
            {activeSession && (
              <>
                <BotAvatar
                  botName={activeSession.bot}
                  displayName={
                    activeSession.bot_display_name ?? activeSession.bot
                  }
                  size="xs"
                />
                <span className="text-sm font-medium">
                  {activeSession.bot_display_name ?? activeSession.bot}
                </span>
                <span className="text-xs text-muted-foreground">
                  Session <code>{activeSession.id}</code>
                </span>
              </>
            )}
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              disabled={!activeSession}
              onClick={handleWorkspaceToggle}
              title="작업 디렉토리 보기"
              aria-label="작업 디렉토리 사이드 패널 토글"
              aria-pressed={workspaceOpen}
            >
              <FolderTree className="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              disabled={!activeSession || activeStream.streaming}
              onClick={handleVoiceOpen}
              title="음성 모드"
              aria-label="음성 모드 전환"
            >
              <Mic className="size-4" />
            </Button>
          </div>
        </header>
        {transientError && (
          <div className="bg-destructive/10 px-4 py-2 text-sm text-destructive">
            {transientError}
          </div>
        )}
        {activeStream.error && (
          <div className="bg-destructive/10 px-4 py-2 text-sm text-destructive">
            {activeStream.error}
          </div>
        )}
        <ScrollArea className="min-h-0 min-w-0 flex-1">
          <div className="flex min-h-full min-w-0 flex-col">
            {messagesLoading && (
              <div className="px-4 py-3 text-sm text-muted-foreground">Loading…</div>
            )}
            {!messagesLoading && activeMessages.length === 0 && (
              <div className="flex flex-1 items-center justify-center px-4 text-center text-sm text-muted-foreground">
                {activeSession
                  ? "Send a message to start the conversation."
                  : "Pick a chat from the left or start a new one."}
              </div>
            )}
            {activeMessages.map((message) => (
              <ChatMessage
                key={message.id}
                role={message.role}
                content={message.content}
                streaming={message.streaming && activeStream.streaming}
                botName={activeSession?.bot ?? null}
                botDisplayName={
                  activeSession?.bot_display_name ?? activeSession?.bot ?? null
                }
                attachments={message.attachments}
                timestamp={message.timestamp}
              />
            ))}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>
        <PromptInput
          bot={activeSession?.bot ?? null}
          sessionId={activeSession?.id ?? null}
          onSubmit={handleSubmit}
          onCancel={handleCancel}
          streaming={activeStream.streaming}
          disabled={!activeSession || activeStream.streaming}
          placeholder={
            activeSession
              ? `Message ${activeSession.bot_display_name || activeSession.bot}…`
              : "Click 'New' on the left to start a chat"
          }
        />
        </>
      </main>
      {voiceMode && activeSession && (
        <aside className="w-72 shrink-0 border-l bg-background">
          <VoiceScreen
            botName={activeSession.bot}
            botDisplayName={activeSession.bot_display_name ?? activeSession.bot}
            voiceState={voice.voiceState}
            partialTranscript={voice.partialTranscript}
            error={voice.error}
            onClose={handleVoiceClose}
          />
        </aside>
      )}
      {workspaceOpen && !voiceMode && activeSession && (
        <aside className="w-72 shrink-0 border-l bg-background">
          <WorkspaceTree
            bot={activeSession.bot}
            sessionId={activeSession.id}
            onClose={handleWorkspaceClose}
          />
        </aside>
      )}
    </div>
  );
}
