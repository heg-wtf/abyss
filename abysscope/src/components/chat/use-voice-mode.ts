"use client";

import * as React from "react";
import { useScribe, CommitStrategy } from "@elevenlabs/react";

const VAD_CONFIG = {
  commitStrategy: CommitStrategy.VAD,
  vadSilenceThresholdSecs: 0.5,
  vadThreshold: 0.2,
  minSpeechDurationMs: 100,
} as const;

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
  const onTranscriptRef = React.useRef(onTranscript);
  onTranscriptRef.current = onTranscript;
  const scribeRef = React.useRef<ReturnType<typeof useScribe> | null>(null);

  const scribe = useScribe({
    modelId: "scribe_v2_realtime",
    languageCode: "ko",
    ...VAD_CONFIG,
    onCommittedTranscript: ({ text }) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      scribeRef.current?.disconnect();
      setVoiceState("processing");
      onTranscriptRef.current(trimmed);
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : String(err));
    },
    onInsufficientAudioActivityError: ({ error: msg }) => {
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
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current.src = "";
      currentAudioRef.current = null;
    }
    try {
      const res = await fetch("/api/chat/scribe-token", { method: "POST" });
      if (!res.ok) throw new Error(`scribe-token ${res.status}`);
      const { token } = (await res.json()) as { token: string };
      await scribeRef.current?.connect({
        token,
        ...VAD_CONFIG,
        microphone: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const stop = React.useCallback(() => {
    scribeRef.current?.disconnect();
  }, []);

  const cancel = React.useCallback(() => {
    scribeRef.current?.disconnect();
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
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
    try {
      const response = await fetch("/api/chat/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) throw new Error(`speak ${response.status}`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      const audio = new Audio(url);
      currentAudioRef.current = audio;
      await new Promise<void>((resolve, reject) => {
        audio.onended = () => resolve();
        audio.onerror = () => reject(new Error("audio playback failed"));
        void audio.play();
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
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
