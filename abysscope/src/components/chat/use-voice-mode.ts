"use client";

import * as React from "react";

export type VoiceState = "idle" | "recording" | "processing" | "speaking";

interface UseVoiceModeOptions {
  onTranscript: (text: string) => void;
}

export interface UseVoiceModeReturn {
  voiceState: VoiceState;
  start: () => void;
  stop: () => void;
  speak: (text: string) => Promise<void>;
  cancel: () => void;
  error: string | null;
}

const SILENCE_THRESHOLD_RMS = 0.01;
const SILENCE_DURATION_MS = 1500;
const MIN_RECORDING_MS = 300;

function computeRms(buffer: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < buffer.length; i++) {
    sum += buffer[i] * buffer[i];
  }
  return Math.sqrt(sum / buffer.length);
}

export function useVoiceMode({ onTranscript }: UseVoiceModeOptions): UseVoiceModeReturn {
  const [voiceState, setVoiceState] = React.useState<VoiceState>("idle");
  const [error, setError] = React.useState<string | null>(null);

  const mediaRecorderRef = React.useRef<MediaRecorder | null>(null);
  const audioContextRef = React.useRef<AudioContext | null>(null);
  const analyserRef = React.useRef<AnalyserNode | null>(null);
  const silenceTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const recordingStartRef = React.useRef<number>(0);
  const chunksRef = React.useRef<BlobPart[]>([]);
  const currentAudioRef = React.useRef<HTMLAudioElement | null>(null);
  const streamRef = React.useRef<MediaStream | null>(null);
  const vadFrameRef = React.useRef<number | null>(null);

  const clearSilenceTimer = () => {
    if (silenceTimerRef.current !== null) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
  };

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (vadFrameRef.current !== null) {
      cancelAnimationFrame(vadFrameRef.current);
      vadFrameRef.current = null;
    }
    if (audioContextRef.current) {
      void audioContextRef.current.close().catch(() => undefined);
      audioContextRef.current = null;
      analyserRef.current = null;
    }
  };

  const transcribe = React.useCallback(async (blob: Blob) => {
    setVoiceState("processing");
    try {
      const form = new FormData();
      form.append("audio", blob, "audio.webm");
      const response = await fetch("/api/chat/transcribe", { method: "POST", body: form });
      if (!response.ok) throw new Error(`transcribe ${response.status}`);
      const data = (await response.json()) as { text: string };
      if (data.text) {
        onTranscript(data.text);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setVoiceState("idle");
    }
  }, [onTranscript]);

  const stopRecording = React.useCallback(() => {
    clearSilenceTimer();
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === "inactive") return;

    const elapsed = Date.now() - recordingStartRef.current;
    if (elapsed < MIN_RECORDING_MS) {
      recorder.stop();
      stopStream();
      setVoiceState("idle");
      return;
    }

    recorder.stop();
    stopStream();
  }, []);

  const startVad = React.useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser) return;

    const buffer = new Float32Array(analyser.fftSize);
    let lastSpeechTime = Date.now();

    const tick = () => {
      analyser.getFloatTimeDomainData(buffer);
      const rms = computeRms(buffer);

      if (rms > SILENCE_THRESHOLD_RMS) {
        lastSpeechTime = Date.now();
        clearSilenceTimer();
      } else if (Date.now() - lastSpeechTime > SILENCE_DURATION_MS) {
        if (silenceTimerRef.current === null) {
          silenceTimerRef.current = setTimeout(() => {
            stopRecording();
          }, 0);
        }
      }

      if (mediaRecorderRef.current?.state === "recording") {
        vadFrameRef.current = requestAnimationFrame(tick);
      }
    };

    vadFrameRef.current = requestAnimationFrame(tick);
  }, [stopRecording]);

  const start = React.useCallback(async () => {
    setError(null);
    cancel();

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("마이크 권한이 필요합니다");
      return;
    }
    streamRef.current = stream;

    const audioCtx = new AudioContext();
    audioContextRef.current = audioCtx;
    const source = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    analyserRef.current = analyser;

    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";

    const recorder = new MediaRecorder(stream, { mimeType });
    mediaRecorderRef.current = recorder;
    chunksRef.current = [];

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };

    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: mimeType });
      chunksRef.current = [];
      void transcribe(blob);
    };

    recorder.start(100);
    recordingStartRef.current = Date.now();
    setVoiceState("recording");
    startVad();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startVad, transcribe]);

  const cancel = React.useCallback(() => {
    clearSilenceTimer();
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.ondataavailable = null;
      recorder.onstop = null;
      recorder.stop();
    }
    mediaRecorderRef.current = null;
    chunksRef.current = [];
    stopStream();

    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current.src = "";
      currentAudioRef.current = null;
    }
    setVoiceState("idle");
  }, []);

  const speak = React.useCallback(async (text: string) => {
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
      if (currentAudioRef.current) {
        URL.revokeObjectURL(currentAudioRef.current.src);
        currentAudioRef.current = null;
      }
      setVoiceState("idle");
    }
  }, []);

  React.useEffect(() => {
    return () => {
      cancel();
    };
  }, [cancel]);

  return { voiceState, start, stop: stopRecording, speak, cancel, error };
}
