/**
 * Client for the abyss chat sidecar HTTP API.
 *
 * The sidecar runs in-process with the Telegram bots (`abyss start`) and
 * binds to 127.0.0.1:3848 by default. Override with `ABYSS_CHAT_API_URL`.
 */

const DEFAULT_BASE = "http://127.0.0.1:3848";

export function getApiBase(): string {
  return process.env.ABYSS_CHAT_API_URL ?? DEFAULT_BASE;
}

export interface BotSummary {
  name: string;
  display_name: string;
  type: string;
}

export interface ChatSession {
  id: string;
  bot: string;
  updated_at: string;
  preview: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export type ChatEvent =
  | { type: "chunk"; text: string }
  | { type: "done"; text: string }
  | { type: "error"; message: string };

async function jsonFetch<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(getApiBase() + path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`abyss-api ${path} ${response.status}: ${text}`);
  }
  return (await response.json()) as T;
}

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(getApiBase() + "/healthz");
    return response.ok;
  } catch {
    return false;
  }
}

export async function listChatBots(): Promise<BotSummary[]> {
  const data = await jsonFetch<{ bots: BotSummary[] }>("/chat/bots");
  return data.bots;
}

export async function listChatSessions(bot: string): Promise<ChatSession[]> {
  const data = await jsonFetch<{ sessions: ChatSession[] }>(
    `/chat/sessions?bot=${encodeURIComponent(bot)}`
  );
  return data.sessions;
}

export async function createChatSession(bot: string): Promise<ChatSession> {
  return jsonFetch<ChatSession>("/chat/sessions", {
    method: "POST",
    body: JSON.stringify({ bot }),
  });
}

export async function deleteChatSession(
  bot: string,
  sessionId: string
): Promise<void> {
  await jsonFetch(`/chat/sessions/${encodeURIComponent(bot)}/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

export async function getChatMessages(
  bot: string,
  sessionId: string
): Promise<ChatMessage[]> {
  const data = await jsonFetch<{ messages: ChatMessage[] }>(
    `/chat/sessions/${encodeURIComponent(bot)}/${encodeURIComponent(sessionId)}/messages`
  );
  return data.messages;
}

export async function cancelChat(bot: string, sessionId: string): Promise<void> {
  await jsonFetch("/chat/cancel", {
    method: "POST",
    body: JSON.stringify({ bot, session_id: sessionId }),
  });
}

/**
 * Forward a streaming chat request to the sidecar and return the raw
 * `Response`. Caller is responsible for piping the body into another
 * `Response` (for Next.js API proxying) or parsing SSE locally.
 */
export async function streamChatRaw(
  bot: string,
  sessionId: string,
  message: string,
  signal?: AbortSignal
): Promise<Response> {
  return fetch(getApiBase() + "/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bot, session_id: sessionId, message }),
    signal,
  });
}

/**
 * Parse an SSE byte stream into discrete `ChatEvent`s. Resilient to
 * messages split across chunk boundaries.
 */
export async function* parseChatEvents(
  body: ReadableStream<Uint8Array>
): AsyncGenerator<ChatEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      for (const line of block.split("\n")) {
        if (line.startsWith("data: ")) {
          try {
            yield JSON.parse(line.slice(6)) as ChatEvent;
          } catch {
            // ignore malformed event
          }
        }
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
}
