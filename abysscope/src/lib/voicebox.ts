/**
 * Voicebox client helpers (Voicebox v0.5.0+).
 *
 * Voicebox runs locally as a separate process (https://voicebox.sh). The
 * dashboard proxies all calls through Next.js API routes so the browser does
 * not need direct access to localhost — easier to mock in tests, uniform
 * origin, single SSRF guard.
 *
 * NOTE: TTS in v0.5.0 requires a `profile_id`. Voice profiles are created in
 * the Voicebox UI (or via `POST /profiles`). The dashboard auto-picks the
 * first available profile; if none exists, the Voice button surfaces a hint.
 */

export const VOICEBOX_BASE = "http://127.0.0.1:17493";

export const STT_LANGUAGE = "ko";
// Whisper variants: base | small | medium | large | turbo. `large` for best
// Korean accuracy; switch to `turbo` for ~2-3x speed at slight accuracy cost.
export const STT_MODEL = "large";

// Voicebox engine codes: qwen | qwen_custom_voice | luxtts | chatterbox |
// chatterbox_turbo | tada | kokoro. `qwen` (Qwen3-TTS) is most balanced for
// Korean + English; `chatterbox` for stronger voice cloning.
export const TTS_ENGINE = "qwen";
export const TTS_LANGUAGE = "ko";
export const TTS_MODEL_SIZE = "1.7B"; // Qwen3-TTS variant

export const HEALTH_TIMEOUT_MS = 2000;

export class VoiceboxError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: string,
    message?: string
  ) {
    super(message ?? `Voicebox request failed: ${status}`);
    this.name = "VoiceboxError";
  }
}

/** Probe Voicebox via the dashboard proxy. */
export async function checkVoiceboxHealth(signal?: AbortSignal): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
    signal?.addEventListener("abort", () => controller.abort(), { once: true });
    const response = await fetch("/api/voice/status", {
      method: "GET",
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (!response.ok) return false;
    const data = (await response.json()) as { ok?: boolean };
    return Boolean(data.ok);
  } catch {
    return false;
  }
}

export interface VoiceProfile {
  id: string;
  name: string;
  language: string;
  voice_type?: string;
  default_engine?: string | null;
}

/** List voice profiles available in Voicebox. */
export async function listVoiceProfiles(
  signal?: AbortSignal
): Promise<VoiceProfile[]> {
  const response = await fetch("/api/voice/profiles", {
    method: "GET",
    signal,
  });
  if (!response.ok) {
    const body = await safeText(response);
    throw new VoiceboxError(response.status, body, "Failed to list profiles");
  }
  const data = await response.json();
  if (!Array.isArray(data)) return [];
  return data as VoiceProfile[];
}

export interface TranscribeOptions {
  language?: string;
  model?: string;
  signal?: AbortSignal;
}

export interface TranscribeResult {
  text: string;
  duration?: number;
}

/**
 * POST audio blob → text. Voicebox `/transcribe` expects multipart with
 * fields: `file` (binary), `language` (optional), `model` (optional).
 */
export async function transcribe(
  audio: Blob,
  options: TranscribeOptions = {}
): Promise<TranscribeResult> {
  const form = new FormData();
  // Voicebox expects the binary part to be named `file` (not `audio`).
  form.append("file", audio, "recording.webm");
  form.append("language", options.language ?? STT_LANGUAGE);
  form.append("model", options.model ?? STT_MODEL);

  const response = await fetch("/api/voice/transcribe", {
    method: "POST",
    body: form,
    signal: options.signal,
  });

  if (!response.ok) {
    const body = await safeText(response);
    throw new VoiceboxError(response.status, body, `Transcribe failed: ${response.status}`);
  }

  const data = (await response.json()) as { text?: string; duration?: number };
  return { text: data.text ?? "", duration: data.duration };
}

export interface SynthesizeOptions {
  /** Voice profile ID (required by Voicebox v0.5.0). */
  profileId: string;
  engine?: string;
  language?: string;
  modelSize?: string;
  signal?: AbortSignal;
}

/**
 * POST text → audio (binary blob). Uses Voicebox `/generate/stream` so the
 * audio bytes come back synchronously (no polling). Requires `profileId`.
 */
export async function synthesize(
  text: string,
  options: SynthesizeOptions
): Promise<Blob> {
  const response = await fetch("/api/voice/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      profile_id: options.profileId,
      text,
      engine: options.engine ?? TTS_ENGINE,
      language: options.language ?? TTS_LANGUAGE,
      model_size: options.modelSize ?? TTS_MODEL_SIZE,
    }),
    signal: options.signal,
  });

  if (!response.ok) {
    const body = await safeText(response);
    throw new VoiceboxError(response.status, body, `Synthesize failed: ${response.status}`);
  }

  return response.blob();
}

async function safeText(response: Response): Promise<string> {
  try {
    return await response.text();
  } catch {
    return "";
  }
}
