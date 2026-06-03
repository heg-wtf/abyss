/**
 * Client for the abyss chat sidecar HTTP API.
 *
 * The sidecar (`abyss start`) serves the mobile PWA and dashboard chat,
 * binding to 127.0.0.1:3848 by default. Override with `ABYSS_CHAT_API_URL`.
 */

const DEFAULT_BASE = "http://127.0.0.1:3848";

export function getApiBase(): string {
  return process.env.ABYSS_CHAT_API_URL ?? DEFAULT_BASE;
}

/**
 * Render a bot's display label.
 *
 * Returns ``"<display_name> (<alias>)"`` when ``alias`` is a
 * non-blank string, otherwise the bare ``display_name``. The single
 * helper keeps formatting consistent across every list / picker / row
 * surface — change the format here once and the whole UI follows.
 *
 * Intentionally NOT used by chat message bubble author labels or Web
 * Push notification titles (per product decision — see plan doc).
 */
export function formatBotLabel(input: {
  display_name?: string | null;
  alias?: string | null;
}): string {
  const name = (input.display_name ?? "").trim();
  const alias = (input.alias ?? "").trim();
  if (!name) return alias;
  if (!alias) return name;
  return `${name} (${alias})`;
}

export interface BotSummary {
  name: string;
  display_name: string;
  type: string;
  /**
   * Optional role / job label. The dashboard renders it as
   * ``"<display_name> (<alias>)"`` in list surfaces (sidebar, drawer,
   * picker) via ``formatBotLabel``. Chat message bubbles and Web
   * Push titles intentionally skip the alias.
   */
  alias?: string | null;
}

export interface ChatSession {
  id: string;
  bot: string;
  bot_display_name?: string;
  /** Optional bot alias — see ``BotSummary.alias`` for semantics. */
  bot_alias?: string | null;
  updated_at: string;
  preview: string;
  /**
   * Optional user-chosen label (e.g. "경제질문"). When absent the UI
   * falls back to ``bot_display_name``. Stored in
   * ``<session_dir>/.session_meta.json`` on the backend.
   */
  custom_name?: string | null;
  /**
   * ISO timestamp of the last time the user opened this session.
   * ``null`` until first read; server stamps it via
   * ``POST /chat/sessions/{bot}/{id}/read``.
   */
  last_read_at?: string | null;
  /** Server-computed: ``updated_at > last_read_at``. */
  unread?: boolean;
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
  | { type: "reset_partial" }
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
 * Stamp ``last_read_at = now()`` for a chat session.
 *
 * Throws on sidecar errors; callers from page mount should wrap in a
 * silent ``.catch`` so a flaky network never blocks the detail view
 * from opening. The Next.js proxy maps thrown errors to 503.
 *
 * Also fires a ``dismiss-notification`` message to the Service
 * Worker so any pending notification for the same session falls out
 * of the tray. Best-effort — never throws on the SW path.
 */
export async function markSessionRead(
  bot: string,
  sessionId: string
): Promise<void> {
  await jsonFetch(
    `/chat/sessions/${encodeURIComponent(bot)}/${encodeURIComponent(sessionId)}/read`,
    { method: "POST" }
  );
  dismissNotification(`session:${bot}:${sessionId}`);
}

/**
 * Numeric feedback signal (1=good, 2=meh, 3=wrong) for a single
 * assistant turn. Phase 1 of the co-evolution roadmap — see
 * ``docs/plan-coevolution-2026-05-19.md``.
 *
 * ``turnId`` is the assistant message's timestamp string from the
 * conversation log header (``YYYY-MM-DD HH:MM:SS UTC``), already
 * present on ``ChatMessage.timestamp``.
 */
export type FeedbackSignal = 1 | 2 | 3;

// ---------------------------------------------------------------------------
// ABOUT_ME — shared user knowledge base
// ---------------------------------------------------------------------------

export type AboutEntryStatus = "confirmed" | "propose";
export type AboutEntryConfidence = "high" | "medium" | "low";

export interface AboutEntry {
  key: string;
  value: string;
  body: string;
  confidence: AboutEntryConfidence;
  source: string;
  added: string;
  last_confirmed: string;
  status: AboutEntryStatus;
  propose_count?: number;
  conflicts_with?: string;
}

export interface AboutCategoryCounts {
  confirmed: number;
  propose: number;
  total: number;
}

export interface AboutMeCategoriesResponse {
  categories: Record<string, AboutCategoryCounts>;
  pending_proposals: number;
}

export const ABOUT_ME_CATEGORIES = [
  "identity",
  "relationships",
  "preferences",
  "routines",
  "current_focus",
  "health",
  "values",
] as const;

export type AboutMeCategory = (typeof ABOUT_ME_CATEGORIES)[number];

export async function fetchAboutMeCategories(): Promise<AboutMeCategoriesResponse> {
  return jsonFetch<AboutMeCategoriesResponse>("/about-me/categories");
}

export async function fetchAboutMeEntries(
  category: AboutMeCategory,
  status?: AboutEntryStatus,
): Promise<AboutEntry[]> {
  const params = status ? `?status=${encodeURIComponent(status)}` : "";
  const data = await jsonFetch<{ entries: AboutEntry[] }>(
    `/about-me/entries/${encodeURIComponent(category)}${params}`,
  );
  return data.entries;
}

export async function approveAboutMeEntry(
  category: AboutMeCategory,
  key: string,
): Promise<void> {
  await jsonFetch(
    `/about-me/entries/${encodeURIComponent(category)}/${encodeURIComponent(key)}/approve`,
    { method: "POST" },
  );
}

export async function rejectAboutMeEntry(
  category: AboutMeCategory,
  key: string,
): Promise<void> {
  await jsonFetch(
    `/about-me/entries/${encodeURIComponent(category)}/${encodeURIComponent(key)}/reject`,
    { method: "POST" },
  );
}

export async function updateAboutMeEntry(
  category: AboutMeCategory,
  key: string,
  patch: { value?: string; body?: string; confidence?: AboutEntryConfidence },
): Promise<void> {
  await jsonFetch(
    `/about-me/entries/${encodeURIComponent(category)}/${encodeURIComponent(key)}`,
    {
      method: "PATCH",
      body: JSON.stringify(patch),
    },
  );
}

export async function createAboutMeEntry(
  category: AboutMeCategory,
  payload: {
    key: string;
    value: string;
    body?: string;
    confidence?: AboutEntryConfidence;
    status?: AboutEntryStatus;
  },
): Promise<void> {
  await jsonFetch(`/about-me/entries/${encodeURIComponent(category)}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function postFeedback(
  bot: string,
  sessionId: string,
  turnId: string,
  signal: FeedbackSignal,
  note?: string,
): Promise<void> {
  await jsonFetch(
    `/chat/sessions/${encodeURIComponent(bot)}/${encodeURIComponent(sessionId)}/feedback`,
    {
      method: "POST",
      body: JSON.stringify({
        turn_id: turnId,
        signal,
        note: note ?? "",
      }),
    },
  );
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
  /** Optional bot alias — see ``BotSummary.alias`` for semantics. */
  bot_alias?: string | null;
  kind: "cron" | "heartbeat";
  job_name: string;
  updated_at: string;
  preview: string;
  last_read_at?: string | null;
  unread?: boolean;
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

/** Routine mark-read — see ``markSessionRead``. */
export async function markRoutineRead(
  bot: string,
  kind: RoutineSummary["kind"],
  jobName: string
): Promise<void> {
  await jsonFetch(
    `/chat/routines/${encodeURIComponent(bot)}/${encodeURIComponent(kind)}/${encodeURIComponent(jobName)}/read`,
    { method: "POST" }
  );
  dismissNotification(`routine:${bot}:${kind}:${jobName}`);
}

/**
 * Tell the active Service Worker to close any notification with the
 * given tag. No-op on the server (SSR), in browsers without a
 * controller (PWA not yet activated), and on the Next.js proxy path
 * where ``navigator`` does not exist. Failure is fine — the worst
 * case is a stale notification in the tray.
 */
function dismissNotification(tag: string): void {
  if (typeof navigator === "undefined") return;
  const controller = navigator.serviceWorker?.controller;
  if (!controller) return;
  try {
    controller.postMessage({ type: "dismiss-notification", tag });
  } catch {
    // ignore
  }
}

/**
 * Reflect the unread count on the PWA app icon (iOS 16.4+, modern
 * Chromium). ``count<=0`` clears the badge. Silently no-ops on
 * browsers that lack ``setAppBadge`` — the in-app dot already covers
 * the unread signal there.
 */
export function setUnreadBadge(count: number): void {
  if (typeof navigator === "undefined") return;
  type BadgeNav = Navigator & {
    setAppBadge?: (count?: number) => Promise<void>;
    clearAppBadge?: () => Promise<void>;
  };
  const nav = navigator as BadgeNav;
  try {
    if (count > 0 && nav.setAppBadge) {
      void nav.setAppBadge(count).catch(() => {});
    } else if (nav.clearAppBadge) {
      void nav.clearAppBadge().catch(() => {});
    }
  } catch {
    // ignore
  }
}

export async function cancelChat(bot: string, sessionId: string): Promise<void> {
  await jsonFetch("/chat/cancel", {
    method: "POST",
    body: JSON.stringify({ bot, session_id: sessionId }),
  });
}

/**
 * Upload a single attachment via the sidecar's multipart endpoint.
 * Returns the stored path that mobile / dashboard chat surfaces pass
 * back to ``/api/chat`` as part of the ``attachments`` array.
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

export interface SelfMdResponse {
  bot: string;
  content: string;
}

export async function fetchSelfMd(bot: string): Promise<SelfMdResponse> {
  return jsonFetch<SelfMdResponse>(`/self/${encodeURIComponent(bot)}`);
}

export async function saveSelfMd(bot: string, content: string): Promise<void> {
  await jsonFetch(`/self/${encodeURIComponent(bot)}`, {
    method: "PUT",
    body: JSON.stringify({ content }),
  });
}

export interface EpisodeRow {
  ts: string;
  date: string;
  kind: "fact" | "event" | "decision" | "change";
  summary: string;
  source_turn: string;
  meta: Record<string, unknown>;
}

export interface EpisodesResponse {
  bot: string;
  episodes: EpisodeRow[];
}

export async function fetchEpisodes(
  bot: string,
  options: { since?: string; kind?: string; limit?: number } = {},
): Promise<EpisodesResponse> {
  const params = new URLSearchParams();
  if (options.since) params.set("since", options.since);
  if (options.kind) params.set("kind", options.kind);
  if (options.limit != null) params.set("limit", String(options.limit));
  const query = params.toString();
  const suffix = query ? `?${query}` : "";
  return jsonFetch<EpisodesResponse>(`/episodes/${encodeURIComponent(bot)}${suffix}`);
}

export interface FactRow {
  id: number;
  subject: string;
  claim: string;
  confidence: number;
  source_turn: string;
  source_episode_id: number | null;
  status: "active" | "retracted" | "superseded";
  created_at: string;
  updated_at: string;
}

export interface FactsResponse {
  bot: string;
  facts: FactRow[];
}

export async function fetchFacts(
  bot: string,
  options: {
    subject?: string;
    minConfidence?: number;
    limit?: number;
    includeRetracted?: boolean;
  } = {},
): Promise<FactsResponse> {
  const params = new URLSearchParams();
  if (options.subject) params.set("subject", options.subject);
  if (options.minConfidence != null)
    params.set("min_confidence", String(options.minConfidence));
  if (options.limit != null) params.set("limit", String(options.limit));
  if (options.includeRetracted) params.set("include_retracted", "true");
  const query = params.toString();
  const suffix = query ? `?${query}` : "";
  return jsonFetch<FactsResponse>(`/facts/${encodeURIComponent(bot)}${suffix}`);
}

export async function retractFact(bot: string, factId: number): Promise<void> {
  await jsonFetch(`/facts/${encodeURIComponent(bot)}/${factId}`, {
    method: "PUT",
    body: JSON.stringify({ action: "retract" }),
  });
}

export interface SkillProposal {
  id: string;
  bot: string;
  candidate_url: string;
  reasons: string[];
  alternative_urls: string[];
  proposed_at: string;
  resolved_at: string | null;
  status: "pending" | "approved" | "rejected";
}

export interface SkillProposalsResponse {
  bot: string;
  proposals: SkillProposal[];
}

export async function fetchSkillProposals(
  bot: string,
  options: { status?: "pending" | "approved" | "rejected" } = {},
): Promise<SkillProposalsResponse> {
  const params = new URLSearchParams();
  if (options.status) params.set("status", options.status);
  const query = params.toString();
  const suffix = query ? `?${query}` : "";
  return jsonFetch<SkillProposalsResponse>(
    `/skill-proposals/${encodeURIComponent(bot)}${suffix}`,
  );
}

export interface ApproveSkillProposalResponse {
  ok: boolean;
  skill_name?: string | null;
  proposal?: SkillProposal;
  error?: string;
  stage?: string;
}

export async function approveSkillProposal(
  bot: string,
  proposalId: string,
): Promise<ApproveSkillProposalResponse> {
  return jsonFetch<ApproveSkillProposalResponse>(
    `/skill-proposals/${encodeURIComponent(bot)}/${encodeURIComponent(proposalId)}/approve`,
    { method: "POST" },
  );
}

export async function rejectSkillProposal(
  bot: string,
  proposalId: string,
): Promise<{ ok: boolean; proposal: SkillProposal }> {
  return jsonFetch<{ ok: boolean; proposal: SkillProposal }>(
    `/skill-proposals/${encodeURIComponent(bot)}/${encodeURIComponent(proposalId)}/reject`,
    { method: "POST" },
  );
}

export interface ProgressEntry {
  ts: string;
  note: string;
  value?: number | null;
}

export interface Goal {
  id: string;
  title: string;
  kpi: string;
  target: string;
  status: "active" | "done" | "archived";
  created_at: string;
  progress: ProgressEntry[];
}

export interface GoalsResponse {
  bot: string;
  goals: Goal[];
}

export async function fetchGoals(
  bot: string,
  options: { status?: "active" | "done" | "archived" } = {},
): Promise<GoalsResponse> {
  const params = new URLSearchParams();
  if (options.status) params.set("status", options.status);
  const query = params.toString();
  const suffix = query ? `?${query}` : "";
  return jsonFetch<GoalsResponse>(`/goals/${encodeURIComponent(bot)}${suffix}`);
}

export async function addGoal(
  bot: string,
  payload: { title: string; kpi?: string; target?: string; id?: string },
): Promise<{ ok: boolean; goal: Goal }> {
  return jsonFetch<{ ok: boolean; goal: Goal }>(
    `/goals/${encodeURIComponent(bot)}`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function updateGoal(
  bot: string,
  goalId: string,
  payload: Partial<Pick<Goal, "title" | "kpi" | "target" | "status">>,
): Promise<{ ok: boolean; goal: Goal }> {
  return jsonFetch<{ ok: boolean; goal: Goal }>(
    `/goals/${encodeURIComponent(bot)}/${encodeURIComponent(goalId)}`,
    { method: "PUT", body: JSON.stringify(payload) },
  );
}

export async function deleteGoal(bot: string, goalId: string): Promise<void> {
  await jsonFetch(
    `/goals/${encodeURIComponent(bot)}/${encodeURIComponent(goalId)}`,
    { method: "DELETE" },
  );
}

export async function recordGoalProgress(
  bot: string,
  goalId: string,
  note: string,
  value?: number | null,
): Promise<{ ok: boolean; entry: ProgressEntry }> {
  const body: Record<string, unknown> = { note };
  if (value != null && Number.isFinite(value)) body.value = value;
  return jsonFetch<{ ok: boolean; entry: ProgressEntry }>(
    `/goals/${encodeURIComponent(bot)}/${encodeURIComponent(goalId)}/progress`,
    { method: "POST", body: JSON.stringify(body) },
  );
}
