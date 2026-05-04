"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  synthesize,
  transcribe,
  VoiceboxError,
} from "@/lib/voicebox";
import {
  DEFAULT_RMS_THRESHOLD,
  DEFAULT_SILENCE_TIMEOUT_MS,
  MIN_RECORDING_BYTES,
  computeRms,
  normalizeAmplitude,
} from "@/lib/voice-rms";

export type VoiceState = "idle" | "listening" | "thinking" | "speaking";

export interface UseVoicePipelineOptions {
  /** Called when STT produces a non-empty transcript. */
  onTranscript?: (text: string) => void;
  /** Called when STT/TTS errors out. */
  onError?: (error: Error) => void;
  /** Override default RMS threshold (silence vs. voice). */
  rmsThreshold?: number;
  /** Override default silence timeout in milliseconds. */
  silenceTimeoutMs?: number;
  /**
   * Voice profile ID required by Voicebox `/generate/stream`. When unset,
   * `speak(text)` is a no-op (so the listening half still works while the
   * caller is loading profiles).
   */
  profileId?: string | null;
}

export interface VoicePipeline {
  state: VoiceState;
  amplitude: number;
  isActive: boolean;
  start: () => Promise<void>;
  stop: () => void;
  /** Queue text for TTS playback; serialized so utterances do not overlap. */
  speak: (text: string) => Promise<void>;
  /** Stop any in-flight speech and clear queue. */
  silence: () => void;
}

interface PendingSpeech {
  text: string;
  resolve: () => void;
  reject: (err: Error) => void;
}

export function useVoicePipeline(
  options: UseVoicePipelineOptions = {}
): VoicePipeline {
  const {
    onTranscript,
    onError,
    rmsThreshold = DEFAULT_RMS_THRESHOLD,
    silenceTimeoutMs = DEFAULT_SILENCE_TIMEOUT_MS,
    profileId = null,
  } = options;
  // Keep latest profileId in a ref so the speech queue picks it up without
  // forcing the queue closure to be recreated on every render.
  const profileIdRef = useRef<string | null>(profileId);
  profileIdRef.current = profileId;

  const [state, setState] = useState<VoiceState>("idle");
  const [amplitude, setAmplitude] = useState(0);
  const [isActive, setIsActive] = useState(false);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rafRef = useRef<number | null>(null);
  const hasSpokenRef = useRef(false);

  const speechQueueRef = useRef<PendingSpeech[]>([]);
  const playbackAudioRef = useRef<HTMLAudioElement | null>(null);
  const playbackUrlRef = useRef<string | null>(null);
  const isPlayingRef = useRef(false);

  // ------------------------------------------------------------------
  // Cleanup helpers
  // ------------------------------------------------------------------

  const releaseMicResources = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      try {
        recorderRef.current.stop();
      } catch {
        /* swallow — already stopped */
      }
    }
    recorderRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (audioCtxRef.current && audioCtxRef.current.state !== "closed") {
      audioCtxRef.current.close().catch(() => {});
    }
    audioCtxRef.current = null;
    analyserRef.current = null;
    hasSpokenRef.current = false;
  }, []);

  const releasePlayback = useCallback(() => {
    if (playbackAudioRef.current) {
      try {
        playbackAudioRef.current.pause();
      } catch {
        /* noop */
      }
      playbackAudioRef.current.src = "";
      playbackAudioRef.current = null;
    }
    if (playbackUrlRef.current) {
      URL.revokeObjectURL(playbackUrlRef.current);
      playbackUrlRef.current = null;
    }
    isPlayingRef.current = false;
  }, []);

  // ------------------------------------------------------------------
  // Speech queue
  // ------------------------------------------------------------------

  const playNextInQueue = useCallback(async () => {
    if (isPlayingRef.current) return;
    const next = speechQueueRef.current.shift();
    if (!next) return;
    isPlayingRef.current = true;
    setState("speaking");

    const currentProfileId = profileIdRef.current;
    if (!currentProfileId) {
      const error = new Error("Voicebox voice profile not configured");
      next.reject(error);
      onError?.(error);
      isPlayingRef.current = false;
      // Drain the rest of the queue with the same error so callers don't hang.
      while (speechQueueRef.current.length > 0) {
        const pending = speechQueueRef.current.shift();
        pending?.reject(error);
      }
      setState((prev) => (prev === "speaking" ? "idle" : prev));
      return;
    }

    try {
      const blob = await synthesize(next.text, { profileId: currentProfileId });
      const url = URL.createObjectURL(blob);
      playbackUrlRef.current = url;
      const audio = new Audio(url);
      playbackAudioRef.current = audio;
      await new Promise<void>((resolve, reject) => {
        audio.onended = () => resolve();
        audio.onerror = () =>
          reject(new Error("audio playback failed"));
        audio.play().catch(reject);
      });
      next.resolve();
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      next.reject(error);
      onError?.(error);
    } finally {
      releasePlayback();
      if (speechQueueRef.current.length > 0) {
        // Continue draining without flipping back to idle.
        playNextInQueue();
      } else {
        setState((prev) => (prev === "speaking" ? "idle" : prev));
      }
    }
  }, [onError, releasePlayback]);

  const speak = useCallback(
    (text: string): Promise<void> => {
      const trimmed = text.trim();
      if (!trimmed) return Promise.resolve();
      return new Promise<void>((resolve, reject) => {
        speechQueueRef.current.push({ text: trimmed, resolve, reject });
        playNextInQueue();
      });
    },
    [playNextInQueue]
  );

  const silence = useCallback(() => {
    speechQueueRef.current.forEach((pending) =>
      pending.reject(new Error("silenced"))
    );
    speechQueueRef.current = [];
    releasePlayback();
    setState((prev) => (prev === "speaking" ? "idle" : prev));
  }, [releasePlayback]);

  // ------------------------------------------------------------------
  // Mic loop
  // ------------------------------------------------------------------

  const handleStop = useCallback(async () => {
    const blob = new Blob(chunksRef.current, { type: "audio/webm" });
    chunksRef.current = [];

    if (blob.size < MIN_RECORDING_BYTES) {
      setState("idle");
      setAmplitude(0);
      return;
    }

    setState("thinking");
    try {
      const result = await transcribe(blob);
      const text = result.text.trim();
      if (text) {
        onTranscript?.(text);
      } else {
        setState("idle");
      }
    } catch (err) {
      const error =
        err instanceof VoiceboxError
          ? err
          : err instanceof Error
            ? err
            : new Error(String(err));
      onError?.(error);
      setState("idle");
    }
  }, [onError, onTranscript]);

  const start = useCallback(async () => {
    if (isActive) return;
    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices?.getUserMedia
    ) {
      onError?.(new Error("getUserMedia is not available"));
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      onError?.(err instanceof Error ? err : new Error(String(err)));
      return;
    }

    const AudioCtor =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext;
    const ctx = new AudioCtor();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);

    const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
    chunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = () => {
      void handleStop();
    };

    streamRef.current = stream;
    audioCtxRef.current = ctx;
    analyserRef.current = analyser;
    recorderRef.current = recorder;
    hasSpokenRef.current = false;
    setIsActive(true);
    setState("listening");

    recorder.start();

    const buffer = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => {
      const currentAnalyser = analyserRef.current;
      const currentRecorder = recorderRef.current;
      if (!currentAnalyser || !currentRecorder) return;

      currentAnalyser.getByteFrequencyData(buffer);
      const rms = computeRms(buffer);
      setAmplitude(normalizeAmplitude(rms));

      if (rms > rmsThreshold) {
        hasSpokenRef.current = true;
        if (silenceTimerRef.current) {
          clearTimeout(silenceTimerRef.current);
          silenceTimerRef.current = null;
        }
      } else if (hasSpokenRef.current && !silenceTimerRef.current) {
        silenceTimerRef.current = setTimeout(() => {
          // recorder.onstop will trigger handleStop()
          if (
            currentRecorder.state !== "inactive"
          ) {
            try {
              currentRecorder.stop();
            } catch {
              /* swallow */
            }
          }
        }, silenceTimeoutMs);
      }

      if (recorderRef.current?.state === "recording") {
        rafRef.current = requestAnimationFrame(tick);
      }
    };
    rafRef.current = requestAnimationFrame(tick);
  }, [handleStop, isActive, onError, rmsThreshold, silenceTimeoutMs]);

  const stop = useCallback(() => {
    releaseMicResources();
    setIsActive(false);
    setAmplitude(0);
    setState((prev) => (prev === "speaking" ? prev : "idle"));
  }, [releaseMicResources]);

  // ------------------------------------------------------------------
  // Cleanup on unmount
  // ------------------------------------------------------------------

  useEffect(() => {
    return () => {
      releaseMicResources();
      releasePlayback();
      speechQueueRef.current.forEach((pending) =>
        pending.reject(new Error("unmounted"))
      );
      speechQueueRef.current = [];
    };
  }, [releaseMicResources, releasePlayback]);

  return {
    state,
    amplitude,
    isActive,
    start,
    stop,
    speak,
    silence,
  };
}
