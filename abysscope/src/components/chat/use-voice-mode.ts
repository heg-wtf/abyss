"use client";

import * as React from "react";
import { useScribe, CommitStrategy } from "@elevenlabs/react";

// Voice-activity detection tuning. Mirrors the *previously*
// test-tuned thresholds from the original RMS-based VAD
// (commit f18789e: ``SILENCE_DURATION_MS = 1500``,
// ``MIN_RECORDING_MS = 300``) and aligns ``vadThreshold`` with the
// ElevenLabs Scribe v2 realtime default (0.4). The earlier 0.2 /
// 0.5 / 100 numbers were guesses landed during the Scribe v2
// migration and were sensitive enough that ambient room noise +
// TTS playback echo could auto-commit a transcript on every
// auto-restart cycle, locking the user into a 듣는중→처리중→응답중
// loop. ``no_verbatim`` strips filler words / false starts /
// disfluencies before we ever see the transcript.
const VAD_CONFIG = {
  commitStrategy: CommitStrategy.VAD,
  vadSilenceThresholdSecs: 1.5,
  vadThreshold: 0.4,
  minSpeechDurationMs: 300,
} as const;

/** Minimum transcript length to forward to the chat. Drops single
 * syllables / spurious commits that survive VAD. */
const MIN_TRANSCRIPT_CHARS = 2;

/**
 * Cold-start mute window after ``voice.start()``. When Scribe
 * reconnects the mic is re-armed instantly, but the phone speaker is
 * still decaying from the just-played TTS and the room hasn't
 * settled. Scribe almost always commits a phantom syllable inside
 * the first ~1.5 s — that's the loop the user has been hitting.
 * Drop every commit that arrives within this window; the user
 * can't realistically be speaking yet because they were listening
 * to the TTS a beat earlier.
 */
const COLD_START_MUTE_MS = 1500;

/** Fire-and-forget STT telemetry so the Python sidecar log captures
 * Scribe v2 realtime activity (the browser → ElevenLabs WebSocket
 * never crosses our server, so we'd otherwise be blind to it). */
function logSttEvent(payload: {
  event: "connect" | "commit" | "disconnect" | "error" | "partial";
  chars?: number;
  latency_ms?: number;
  language_code?: string;
  detail?: string;
}): void {
  // ``keepalive: true`` so the request survives a tab close. The
  // returned Promise is intentionally not awaited.
  void fetch("/api/chat/log-stt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    keepalive: true,
  }).catch(() => {
    // Telemetry must never break voice mode.
  });
}

export type VoiceState = "idle" | "recording" | "processing" | "speaking";

interface UseVoiceModeOptions {
  onTranscript: (text: string) => void;
}

export interface UseVoiceModeReturn {
  voiceState: VoiceState;
  partialTranscript: string;
  start: () => void;
  stop: () => void;
  speak: (text: string) => Promise<void>;
  cancel: () => void;
  error: string | null;
}

export function useVoiceMode({ onTranscript }: UseVoiceModeOptions): UseVoiceModeReturn {
  const [voiceState, setVoiceState] = React.useState<VoiceState>("idle");
  const [error, setError] = React.useState<string | null>(null);
  const currentAudioRef = React.useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = React.useRef<string | null>(null);
  // Controller for the in-flight /api/chat/speak fetch. ``cancel()``
  // aborts it so the X button kills audio playback even when the
  // request hasn't returned yet.
  const speakAbortRef = React.useRef<AbortController | null>(null);
  // ``performance.now()`` value at the moment Scribe's mic re-armed.
  // ``onCommittedTranscript`` checks this against
  // ``COLD_START_MUTE_MS`` to drop phantom commits caused by TTS
  // speaker decay / ambient noise during the re-arm window.
  const startedAtRef = React.useRef<number>(0);
  // Persistent ``<audio>`` element reused across every TTS playback.
  // iOS Safari ties autoplay authorization to a specific element
  // instance — once an element has been ``.play()``'d during a user
  // gesture, future ``.play()`` calls on the same element succeed
  // without re-prompting. Recreating ``new Audio(url)`` on every
  // speak() call (the previous behaviour) meant each fresh element
  // was unauthorized, ``audio.play()`` rejected with
  // ``NotAllowedError``, and the user heard silence.
  const audioElementRef = React.useRef<HTMLAudioElement | null>(null);
  const onTranscriptRef = React.useRef(onTranscript);
  onTranscriptRef.current = onTranscript;
  const scribeRef = React.useRef<ReturnType<typeof useScribe> | null>(null);

  const scribe = useScribe({
    modelId: "scribe_v2_realtime",
    languageCode: "ko",
    // Drop filler words, false starts, and disfluencies before
    // they reach the chat — same option ElevenLabs added for Scribe
    // v2 batch + realtime. Gets us cleaner Korean transcripts
    // without a post-hoc cleanup step on our side.
    noVerbatim: true,
    ...VAD_CONFIG,
    onCommittedTranscript: ({ text }) => {
      const trimmed = text.trim();
      const elapsed = performance.now() - startedAtRef.current;
      if (elapsed < COLD_START_MUTE_MS) {
        // Phantom commit during the mic re-arm window — almost
        // always TTS speaker decay or ambient noise. Drop silently
        // (visible only in the server STT log).
        logSttEvent({
          event: "partial",
          chars: trimmed.length,
          latency_ms: elapsed,
          detail: `cold-start drop "${trimmed.slice(0, 40)}"`,
        });
        return;
      }
      if (trimmed.length < MIN_TRANSCRIPT_CHARS) {
        logSttEvent({
          event: "partial",
          chars: trimmed.length,
          latency_ms: elapsed,
          detail: "too short",
        });
        return;
      }
      scribeRef.current?.disconnect();
      setVoiceState("processing");
      logSttEvent({
        event: "commit",
        chars: trimmed.length,
        latency_ms: elapsed,
        language_code: "ko",
      });
      onTranscriptRef.current(trimmed);
    },
    onError: (err) => {
      const message = err instanceof Error ? err.message : String(err);
      logSttEvent({ event: "error", detail: message });
      setError(message);
    },
    onInsufficientAudioActivityError: ({ error: msg }) => {
      logSttEvent({ event: "error", detail: `insufficient_audio: ${msg}` });
      setError(`음성 감지 실패: ${msg}`);
    },
  });

  scribeRef.current = scribe;

  // Map scribe status → voiceState (skip while speaking or processing)
  React.useEffect(() => {
    if (voiceState === "speaking" || voiceState === "processing") return;
    if (scribe.status === "connected" || scribe.status === "transcribing") {
      setVoiceState("recording");
    } else if (scribe.status === "disconnected" || scribe.status === "error") {
      setVoiceState("idle");
    }
  }, [scribe.status, voiceState]);

  const start = React.useCallback(async () => {
    setError(null);
    // iOS Safari audio unlock — must instantiate the ``<audio>``
    // element and call ``play()`` *synchronously* during the user
    // gesture (mic tap) for subsequent autoplay to be allowed.
    // Empty-src play() rejects harmlessly but flags the element as
    // user-authorized. We reuse the same element in ``speak()``
    // below; iOS preserves the authorization for that instance.
    if (!audioElementRef.current) {
      const element = new Audio();
      element.preload = "auto";
      audioElementRef.current = element;
    }
    audioElementRef.current.play().catch(() => {
      // Empty audio play always rejects — fine, the unlock side
      // effect already happened.
    });

    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current.src = "";
      currentAudioRef.current = null;
    }
    // Reset the cold-start clock *before* the connect so phantom
    // commits during the re-arm window get rejected by
    // ``onCommittedTranscript``.
    startedAtRef.current = performance.now();
    const tokenStart = performance.now();
    try {
      const res = await fetch("/api/chat/scribe-token", { method: "POST" });
      if (!res.ok) throw new Error(`scribe-token ${res.status}`);
      const { token } = (await res.json()) as { token: string };
      await scribeRef.current?.connect({
        token,
        ...VAD_CONFIG,
        microphone: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      logSttEvent({
        event: "connect",
        latency_ms: performance.now() - tokenStart,
        language_code: "ko",
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      logSttEvent({ event: "error", detail: `start failed: ${message}` });
      setError(message);
    }
  }, []);

  const stop = React.useCallback(() => {
    scribeRef.current?.disconnect();
  }, []);

  const cancel = React.useCallback(() => {
    scribeRef.current?.disconnect();
    if (speakAbortRef.current) {
      speakAbortRef.current.abort();
      speakAbortRef.current = null;
    }
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current.src = "";
      currentAudioRef.current = null;
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setVoiceState("idle");
    setError(null);
  }, []);

  const speak = React.useCallback(async (text: string) => {
    scribeRef.current?.disconnect();
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }
    setVoiceState("speaking");
    setError(null);
    const controller = new AbortController();
    speakAbortRef.current?.abort();
    speakAbortRef.current = controller;
    try {
      const response = await fetch("/api/chat/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (!response.ok) {
        const detail = await response.text().catch(() => "");
        throw new Error(`speak ${response.status}${detail ? `: ${detail}` : ""}`);
      }
      const blob = await response.blob();
      if (controller.signal.aborted) return;
      // Force a known MIME so iOS Safari's audio element doesn't
      // refuse the blob when the server response omits the type.
      const audioBlob =
        blob.type && blob.type !== ""
          ? blob
          : new Blob([blob], { type: "audio/mpeg" });
      const url = URL.createObjectURL(audioBlob);
      objectUrlRef.current = url;
      // Reuse the iOS-unlocked element from ``start()``. Falling
      // back to ``new Audio()`` here would mean a fresh
      // unauthorized element on the very first ``speak()``.
      const audio = audioElementRef.current ?? new Audio();
      audioElementRef.current = audio;
      audio.preload = "auto";
      audio.src = url;
      currentAudioRef.current = audio;
      await new Promise<void>((resolve, reject) => {
        audio.onended = () => resolve();
        audio.onerror = () => {
          const mediaError = audio.error;
          reject(
            new Error(
              `audio playback failed${
                mediaError ? ` (code ${mediaError.code}: ${mediaError.message})` : ""
              }`,
            ),
          );
        };
        // ``play()`` returns a Promise that rejects with
        // ``NotAllowedError`` (iOS autoplay block), ``AbortError``
        // (concurrent play), or other DOMException values. Without
        // this catch the outer ``await`` hangs forever because the
        // element never reaches ``onended`` or ``onerror``.
        audio.play().catch((playError: unknown) => {
          reject(
            playError instanceof Error
              ? playError
              : new Error(`audio play rejected: ${String(playError)}`),
          );
        });
      });
    } catch (err) {
      // Aborts come through as ``AbortError`` — that's our own
      // ``cancel()`` killing the in-flight speak, not an actual
      // failure. Don't surface it as a user-visible error.
      const name = (err as { name?: string } | null)?.name;
      if (name !== "AbortError") {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (speakAbortRef.current === controller) {
        speakAbortRef.current = null;
      }
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
      currentAudioRef.current = null;
      setVoiceState("idle");
    }
  }, []);

  React.useEffect(() => {
    return () => {
      scribeRef.current?.disconnect();
    };
  }, []);

  return { voiceState, partialTranscript: scribe.partialTranscript, start, stop, speak, cancel, error };
}
