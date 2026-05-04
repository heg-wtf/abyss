"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  synthesize,
  transcribe,
  VoiceboxError,
} from "@/lib/voicebox";
import { isLikelyWhisperHallucination } from "@/lib/whisper-hallucination";
import {
  DEFAULT_RMS_THRESHOLD,
  DEFAULT_SILENCE_TIMEOUT_MS,
  MIN_RECORDING_BYTES,
  QUIET_PEAK_RMS_THRESHOLD,
  computeTimeDomainRms,
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
    // NOTE: hasSpokenRef is NOT cleared here — handleStop runs async after
    // recorder.onstop and needs to read its final value. handleStop resets
    // it once consumed.
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
      // Profile not yet loaded (or none exists) — silently drop without
      // surfacing as an error. The UI already shows a separate hint when
      // the profile list is empty.
      next.resolve();
      isPlayingRef.current = false;
      while (speechQueueRef.current.length > 0) {
        const pending = speechQueueRef.current.shift();
        pending?.resolve();
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

  const recorderMimeRef = useRef<string>("");
  // Tracks whether the in-flight take ends because the user pressed the
  // stop button (manual) or because silence-detection fired (auto). On
  // manual stop we trust the user and skip the speech-detected gate.
  const stopReasonRef = useRef<"auto" | "manual">("auto");
  // Peak RMS observed during the current take — used to detect "audio is
  // way too quiet, Whisper will only hallucinate" and skip transcription.
  const peakRmsRef = useRef<number>(0);

  const handleStop = useCallback(async () => {
    const blobType = recorderMimeRef.current || "audio/webm";
    const blob = new Blob(chunksRef.current, { type: blobType });
    const userActuallySpoke = hasSpokenRef.current;
    const reason = stopReasonRef.current;
    const peakRms = peakRmsRef.current;
    chunksRef.current = [];
    hasSpokenRef.current = false;
    stopReasonRef.current = "auto";
    peakRmsRef.current = 0;

    const tooShort = blob.size < MIN_RECORDING_BYTES;
    const tooQuiet = peakRms < QUIET_PEAK_RMS_THRESHOLD;
    // Auto-stop without speech detection -> nothing was said, skip silently.
    if (reason === "auto" && !userActuallySpoke) {
      setState("idle");
      setAmplitude(0);
      return;
    }
    if (tooShort) {
      setState("idle");
      setAmplitude(0);
      onError?.(new Error("녹음이 너무 짧습니다."));
      return;
    }
    // Manual stop with extremely quiet take -> Whisper will just hallucinate
    // YouTube boilerplate. Surface a real hint instead of swallowing.
    if (tooQuiet) {
      setState("idle");
      setAmplitude(0);
      onError?.(new Error("음성이 너무 작습니다. 마이크를 가까이 하고 다시 시도해주세요."));
      return;
    }

    setState("thinking");
    try {
      const result = await transcribe(blob);
      const text = result.text.trim();
      if (!text) {
        setState("idle");
        onError?.(new Error("음성을 인식하지 못했어요. 다시 시도해주세요."));
        return;
      }
      if (isLikelyWhisperHallucination(text)) {
        setState("idle");
        onError?.(
          new Error("음성을 알아듣지 못했어요. 더 가까이서 또렷하게 말해주세요.")
        );
        return;
      }
      onTranscript?.(text);
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

    // Prefer MP4/AAC because Voicebox v0.5.0 reliably decodes it; webm/opus
    // sometimes hits "Could not decode" depending on the bundled ffmpeg build.
    const mimeCandidates = [
      "audio/mp4;codecs=mp4a.40.2",
      "audio/mp4",
      "audio/webm;codecs=opus",
      "audio/webm",
    ];
    const pickedMime =
      mimeCandidates.find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
    recorderMimeRef.current = pickedMime;
    const recorder = pickedMime
      ? new MediaRecorder(stream, { mimeType: pickedMime })
      : new MediaRecorder(stream);
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

    // Time-domain VAD — much more reliable than frequency-bin RMS for
    // detecting "is the user speaking right now".
    const buffer = new Uint8Array(analyser.fftSize);
    const tick = () => {
      const currentAnalyser = analyserRef.current;
      const currentRecorder = recorderRef.current;
      if (!currentAnalyser || !currentRecorder) return;

      currentAnalyser.getByteTimeDomainData(buffer);
      const rms = computeTimeDomainRms(buffer);
      setAmplitude(normalizeAmplitude(rms));
      if (rms > peakRmsRef.current) peakRmsRef.current = rms;

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
    // Tell handleStop the user explicitly ended the take, so it bypasses
    // the silence-detection gate even if RMS never crossed the threshold.
    stopReasonRef.current = "manual";
    // releaseMicResources stops the recorder, which queues an onstop event
    // -> handleStop in the next microtask; chunks survive on chunksRef.
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
