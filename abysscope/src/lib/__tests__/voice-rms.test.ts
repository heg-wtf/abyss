import { describe, expect, it } from "vitest";
import { computeRms, normalizeAmplitude } from "@/lib/voice-rms";

describe("computeRms", () => {
  it("returns 0 for empty buffer", () => {
    expect(computeRms(new Uint8Array(0))).toBe(0);
  });

  it("returns 0 for all-zero buffer", () => {
    expect(computeRms(new Uint8Array([0, 0, 0, 0]))).toBe(0);
  });

  it("returns non-zero for buffer with energy", () => {
    const buf = new Uint8Array([10, 20, 30, 40]);
    expect(computeRms(buf)).toBeGreaterThan(0);
  });

  it("matches the manual RMS formula", () => {
    const buf = new Uint8Array([3, 4]);
    // sqrt((9 + 16) / 2) = sqrt(12.5)
    expect(computeRms(buf)).toBeCloseTo(Math.sqrt(12.5), 6);
  });
});

describe("normalizeAmplitude", () => {
  it("clamps below 0", () => {
    expect(normalizeAmplitude(-10)).toBe(0);
  });

  it("clamps above 1", () => {
    expect(normalizeAmplitude(1024)).toBe(1);
  });

  it("scales 64 -> 0.5", () => {
    expect(normalizeAmplitude(64)).toBeCloseTo(0.5);
  });
});
