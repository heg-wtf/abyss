/**
 * Pure helpers for voice pipeline logic. Extracted so we can unit-test in
 * Node without mocking the entire Web Audio API.
 */

/** Frequency-bin RMS over an analyser buffer (legacy magnitude-based VAD). */
export function computeRms(buffer: Uint8Array): number {
  if (buffer.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < buffer.length; i++) {
    sum += buffer[i] * buffer[i];
  }
  return Math.sqrt(sum / buffer.length);
}

/**
 * Time-domain RMS over an `AnalyserNode.getByteTimeDomainData` buffer.
 *
 * Each sample is 0..255 with 128 representing PCM zero. The RMS is the
 * deviation from that midpoint, which is what voice activity detection
 * cares about. Range: 0 (silence) .. ~128 (max).
 */
export function computeTimeDomainRms(buffer: Uint8Array): number {
  if (buffer.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < buffer.length; i++) {
    const deviation = buffer[i] - 128;
    sum += deviation * deviation;
  }
  return Math.sqrt(sum / buffer.length);
}

/** Normalize RMS magnitude into 0..1 for UI amplitude indicators. */
export function normalizeAmplitude(rms: number): number {
  return Math.min(1, Math.max(0, rms / 64));
}

export interface VoiceGateState {
  /** Has the user started speaking at least once during this take? */
  hasSpoken: boolean;
  /** Timer ID for the silence countdown, or null when not counting. */
  silenceTimer: ReturnType<typeof setTimeout> | null;
}

// Time-domain RMS threshold — laptop mic at conversational level produces
// values around 8-30. Below ~4 is effectively silence.
export const DEFAULT_RMS_THRESHOLD = 5;
export const DEFAULT_SILENCE_TIMEOUT_MS = 1200;
// Audio container headers can occupy ~1-2 KB on their own; require enough
// bytes to be confident a real recording exists before we transcribe.
export const MIN_RECORDING_BYTES = 5000;
