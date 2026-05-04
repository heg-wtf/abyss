/**
 * Voicebox client helpers.
 *
 * Voicebox runs locally as a separate process (https://voicebox.sh). The
 * dashboard proxies STT/TTS calls through Next.js API routes so the browser
 * does not need direct access to localhost:47390 (uniform origin, easier to
 * mock in tests).
 *
 * SSRF guard: VOICEBOX_BASE is a hardcoded localhost URL — never derived from
 * user input.
 */

export const VOICEBOX_BASE = "http://localhost:47390";

export const STT_LANGUAGE = "ko";
// Whisper large-v3 — best Korean accuracy, also strong English. Trades ~1-2s
// extra latency on M-series for noticeably better Korean transcription.
export const STT_MODEL = "large-v3";

// Qwen3-TTS — most consistent quality across Korean + English (one of its 10
// official languages). Switch to "chatterbox" if you want stronger emotional
// expressiveness or zero-shot voice cloning at the cost of cross-language
// uniformity.
export const TTS_ENGINE = "qwen3-tts";
export const TTS_LANGUAGE = "ko";

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

/**
 * Probe Voicebox via the dashboard proxy. Returns true when the server is
 * reachable and healthy.
 */
export async function checkVoiceboxHealth(signal?: AbortSignal): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
    // Chain the caller's signal so component unmounts can abort early.
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

export interface TranscribeOptions {
  language?: string;
  model?: string;
  signal?: AbortSignal;
}

export interface TranscribeResult {
  text: string;
}

/**
 * POST audio blob → text via the dashboard proxy. The blob can be any format
 * Voicebox accepts (`audio/webm`, `audio/wav`, `audio/mp4`, ...).
 */
export async function transcribe(
  audio: Blob,
  options: TranscribeOptions = {}
): Promise<TranscribeResult> {
  const form = new FormData();
  form.append("audio", audio, "recording.webm");
  form.append("language", options.language ?? STT_LANGUAGE);
  form.append("model_size", options.model ?? STT_MODEL);

  const response = await fetch("/api/voice/transcribe", {
    method: "POST",
    body: form,
    signal: options.signal,
  });

  if (!response.ok) {
    const body = await safeText(response);
    throw new VoiceboxError(response.status, body, `Transcribe failed: ${response.status}`);
  }

  const data = (await response.json()) as { text?: string };
  return { text: data.text ?? "" };
}

export interface SynthesizeOptions {
  voiceId?: string;
  engine?: string;
  language?: string;
  signal?: AbortSignal;
}

/**
 * POST text → audio (binary blob) via the dashboard proxy.
 */
export async function synthesize(
  text: string,
  options: SynthesizeOptions = {}
): Promise<Blob> {
  const response = await fetch("/api/voice/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      voice_id: options.voiceId,
      engine: options.engine ?? TTS_ENGINE,
      language: options.language ?? TTS_LANGUAGE,
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
