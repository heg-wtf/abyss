"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export type OrbState = "idle" | "listening" | "thinking" | "speaking";

interface Props {
  state: OrbState;
  size?: number;
  /** 0..1 normalized mic input amplitude (only used in `listening` state). */
  amplitude?: number;
  className?: string;
}

const STATE_LABEL: Record<OrbState, string> = {
  idle: "대기 중",
  listening: "듣는 중",
  thinking: "생각 중",
  speaking: "말하는 중",
};

const STATE_GRADIENT: Record<OrbState, string> = {
  idle: "from-slate-700 via-slate-600 to-slate-800",
  listening: "from-cyan-400 via-sky-500 to-blue-700",
  thinking: "from-violet-500 via-fuchsia-500 to-indigo-700",
  speaking: "from-emerald-400 via-teal-500 to-cyan-700",
};

export function VoiceOrbVoid({
  state,
  size = 240,
  amplitude = 0,
  className,
}: Props) {
  const ringScale = 1 + Math.min(Math.max(amplitude, 0), 1) * 0.25;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={`Voice orb: ${STATE_LABEL[state]}`}
      data-state={state}
      className={cn(
        "relative flex items-center justify-center select-none",
        className
      )}
      style={{ width: size, height: size }}
    >
      {/* Outer reactive ring (only animates while listening) */}
      <div
        aria-hidden
        className={cn(
          "absolute inset-0 rounded-full bg-gradient-to-br opacity-40 blur-2xl",
          STATE_GRADIENT[state]
        )}
        style={{
          transform: state === "listening" ? `scale(${ringScale})` : undefined,
          animation:
            state === "listening"
              ? "voice-orb-wave 1.6s ease-in-out infinite"
              : state === "speaking"
                ? "voice-orb-pulse 0.9s ease-in-out infinite"
                : state === "idle"
                  ? "voice-orb-breathe 4s ease-in-out infinite"
                  : undefined,
        }}
      />

      {/* Mid layer rotating gradient for thinking */}
      <div
        aria-hidden
        className={cn(
          "absolute inset-4 rounded-full bg-gradient-to-tr opacity-80 blur-md",
          STATE_GRADIENT[state]
        )}
        style={{
          animation:
            state === "thinking"
              ? "voice-orb-rotate 6s linear infinite"
              : state === "speaking"
                ? "voice-orb-pulse 0.9s ease-in-out infinite"
                : state === "listening"
                  ? "voice-orb-pulse 1.2s ease-in-out infinite"
                  : undefined,
        }}
      />

      {/* Core orb */}
      <div
        aria-hidden
        className={cn(
          "absolute inset-8 rounded-full bg-gradient-to-br shadow-2xl",
          STATE_GRADIENT[state]
        )}
        style={{
          animation:
            state === "idle"
              ? "voice-orb-breathe 4s ease-in-out infinite"
              : undefined,
        }}
      />

      {/* Specular highlight */}
      <div
        aria-hidden
        className="absolute inset-10 rounded-full bg-gradient-to-br from-white/40 via-white/10 to-transparent"
      />

      <span className="sr-only">{STATE_LABEL[state]}</span>
    </div>
  );
}
