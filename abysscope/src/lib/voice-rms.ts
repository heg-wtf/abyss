/**
 * Pure helpers for voice pipeline logic. Extracted so we can unit-test in
 * Node without mocking the entire Web Audio API.
 */

/** Frequency-bin RMS over an analyser buffer. */
export function computeRms(buffer: Uint8Array): number {
  if (buffer.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < buffer.length; i++) {
    sum += buffer[i] * buffer[i];
  }
  return Math.sqrt(sum / buffer.length);
}

/** Normalize RMS magnitude (0..255) into 0..1 for UI amplitude indicators. */
export function normalizeAmplitude(rms: number): number {
  return Math.min(1, Math.max(0, rms / 128));
}

export interface VoiceGateState {
  /** Has the user started speaking at least once during this take? */
  hasSpoken: boolean;
  /** Timer ID for the silence countdown, or null when not counting. */
  silenceTimer: ReturnType<typeof setTimeout> | null;
}

export const DEFAULT_RMS_THRESHOLD = 18;
export const DEFAULT_SILENCE_TIMEOUT_MS = 900;
export const MIN_RECORDING_BYTES = 1000;
