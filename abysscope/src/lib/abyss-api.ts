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
  bot_display_name?: string;
  updated_at: string;
  preview: string;
  /**
   * Optional user-chosen label (e.g. "경제질문"). When absent the UI
   * falls back to ``bot_display_name``. Stored in
   * ``<session_dir>/.session_meta.json`` on the backend.
   */
  custom_name?: string | null;
}

export interface ChatAttachmentRef {
  display_name: string;
  real_name: string;
  mime: string;
  url: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  attachments?: ChatAttachmentRef[];
}

/** Attachment record returned by `POST /chat/upload`. */
export interface UploadedAttachment {
  path: string;
  display_name: string;
  mime: string;
  size: number;
}

export const ALLOWED_UPLOAD_MIME_TYPES = [
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
  "application/pdf",
] as const;

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const MAX_UPLOADS_PER_MESSAGE = 5;

export type ChatEvent =
  | { type: "chunk"; text: string }
  | { type: "done"; text: string }
  | { type: "error"; message: string }
  | {
      type: "command_result";
      command: string;
      text: string;
      file?: { name: string; path: string; url: string };
    };

/**
 * Thrown when the sidecar replies with a non-2xx status. Lets callers
 * forward upstream 4xx errors verbatim instead of collapsing every
 * failure into a 503.
 */
export class UpstreamError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: string,
    public readonly contentType: string
  ) {
    super(`upstream ${status}: ${body.slice(0, 200)}`);
    this.name = "UpstreamError";
  }
}

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
    throw new UpstreamError(
      response.status,
      text,
      response.headers.get("Content-Type") ?? "application/json"
    );
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

export async function renameChatSession(
  bot: string,
  sessionId: string,
  name: string
): Promise<{ id: string; bot: string; custom_name: string | null }> {
  return jsonFetch<{ id: string; bot: string; custom_name: string | null }>(
    `/chat/sessions/${encodeURIComponent(bot)}/${encodeURIComponent(sessionId)}/rename`,
    {
      method: "POST",
      body: JSON.stringify({ name }),
    }
  );
}

export interface SlashCommandSpec {
  name: string;
  description: string;
  usage: string;
}

export async function listSlashCommands(): Promise<SlashCommandSpec[]> {
  const data = await jsonFetch<{ commands: SlashCommandSpec[] }>(
    "/chat/commands"
  );
  return data.commands;
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

/**
 * A scheduled-run surface: cron job or heartbeat session. Shares the
 * core "bot + last-run + preview" shape with ``ChatSession`` so the
 * mobile Routines tab can use the same row component, with two extra
 * fields (``kind`` / ``job_name``) for the detail-page URL.
 */
export interface RoutineSummary {
  bot: string;
  bot_display_name: string;
  kind: "cron" | "heartbeat";
  job_name: string;
  updated_at: string;
  preview: string;
}

export async function listRoutines(): Promise<RoutineSummary[]> {
  const data = await jsonFetch<{ routines: RoutineSummary[] }>(
    "/chat/routines"
  );
  return data.routines;
}

export async function getRoutineMessages(
  bot: string,
  kind: RoutineSummary["kind"],
  jobName: string
): Promise<ChatMessage[]> {
  const data = await jsonFetch<{ messages: ChatMessage[] }>(
    `/chat/routines/${encodeURIComponent(bot)}/${encodeURIComponent(kind)}/${encodeURIComponent(jobName)}/messages`
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
 *
 * `attachments` is the list of `path` values returned by
 * `uploadAttachment()`. Empty list omits the field entirely.
 */
export async function streamChatRaw(
  bot: string,
  sessionId: string,
  message: string,
  signal?: AbortSignal,
  attachments: string[] = []
): Promise<Response> {
  const body: Record<string, unknown> = {
    bot,
    session_id: sessionId,
    message,
  };
  if (attachments.length > 0) {
    body.attachments = attachments;
  }
  return fetch(getApiBase() + "/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}

/**
 * Upload a single attachment via the sidecar's multipart endpoint.
 * Returns the stored path that should be passed to `streamChatRaw`.
 *
 * Throws `UpstreamError` for HTTP failures, plain `Error` for network errors.
 */
export async function uploadAttachment(
  bot: string,
  sessionId: string,
  file: File,
  signal?: AbortSignal
): Promise<UploadedAttachment> {
  const form = new FormData();
  form.append("bot", bot);
  form.append("session_id", sessionId);
  form.append("file", file, file.name);

  const response = await fetch("/api/chat/upload", {
    method: "POST",
    body: form,
    signal,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new UpstreamError(
      response.status,
      text,
      response.headers.get("Content-Type") ?? "application/json"
    );
  }
  return (await response.json()) as UploadedAttachment;
}

/** URL for fetching a previously uploaded file via the dashboard proxy. */
export function attachmentUrl(
  bot: string,
  sessionId: string,
  realName: string
): string {
  return `/api/chat/sessions/${encodeURIComponent(bot)}/${encodeURIComponent(sessionId)}/file/${encodeURIComponent(realName)}`;
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
