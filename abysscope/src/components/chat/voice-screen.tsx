"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { BotAvatar } from "@/components/bot-avatar";
import type { VoiceState } from "./use-voice-mode";

interface Props {
  botName: string;
  botDisplayName: string;
  voiceState: VoiceState;
  error: string | null;
  onClose: () => void;
  onOrbClick: () => void;
}

const STATE_LABEL: Record<VoiceState, string> = {
  idle: "탭하여 말하기",
  recording: "듣는 중...",
  processing: "처리 중...",
  speaking: "응답 중...",
};

export function VoiceScreen({
  botName,
  botDisplayName,
  voiceState,
  error,
  onClose,
  onOrbClick,
}: Props) {
  return (
    <div className="flex h-full flex-col items-center justify-between bg-background px-6 py-8">
      {/* Header */}
      <div className="flex w-full items-center justify-between">
        <div className="flex items-center gap-3">
          <BotAvatar botName={botName} displayName={botDisplayName} size="sm" />
          <span className="text-sm font-medium">{botDisplayName}</span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          aria-label="음성 모드 종료"
        >
          <X className="size-5" />
        </Button>
      </div>

      {/* Orb */}
      <button
        type="button"
        onClick={onOrbClick}
        className="group relative flex items-center justify-center focus:outline-none"
        aria-label={STATE_LABEL[voiceState]}
      >
        {/* Outer pulse rings */}
        <span
          className={cn(
            "absolute inline-flex rounded-full opacity-0",
            voiceState === "recording" &&
              "size-48 animate-ping bg-red-500/20 opacity-100 duration-1000",
            voiceState === "speaking" &&
              "size-48 animate-ping bg-blue-500/20 opacity-100 duration-700",
          )}
        />
        <span
          className={cn(
            "absolute inline-flex rounded-full opacity-0",
            voiceState === "recording" &&
              "size-36 animate-ping bg-red-500/30 opacity-100 duration-700",
            voiceState === "speaking" &&
              "size-36 animate-ping bg-blue-500/30 opacity-100 duration-500",
          )}
        />

        {/* Core orb */}
        <span
          className={cn(
            "relative flex size-28 items-center justify-center rounded-full transition-all duration-300",
            voiceState === "idle" &&
              "bg-muted/80 shadow-lg group-hover:bg-muted",
            voiceState === "recording" &&
              "bg-red-500 shadow-[0_0_40px_rgba(239,68,68,0.5)]",
            voiceState === "processing" &&
              "bg-muted/80 shadow-lg",
            voiceState === "speaking" &&
              "bg-blue-500 shadow-[0_0_40px_rgba(59,130,246,0.5)]",
          )}
        >
          {voiceState === "processing" ? (
            <span className="size-10 animate-spin rounded-full border-4 border-foreground/20 border-t-foreground" />
          ) : (
            <MicWaveIcon voiceState={voiceState} />
          )}
        </span>
      </button>

      {/* Status + error */}
      <div className="flex flex-col items-center gap-2">
        {error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : (
          <p className="text-sm text-muted-foreground">{STATE_LABEL[voiceState]}</p>
        )}
        {(voiceState === "recording" || voiceState === "speaking") && (
          <Button variant="outline" size="sm" onClick={onClose}>
            취소
          </Button>
        )}
      </div>
    </div>
  );
}

function MicWaveIcon({ voiceState }: { voiceState: VoiceState }) {
  const isActive = voiceState === "recording" || voiceState === "speaking";
  return (
    <svg
      viewBox="0 0 40 40"
      className={cn("size-12", isActive ? "text-white" : "text-foreground/60")}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
    >
      {/* Mic body */}
      <rect x="14" y="4" width="12" height="20" rx="6" />
      {/* Mic stand */}
      <path d="M8 20a12 12 0 0 0 24 0" />
      <line x1="20" y1="32" x2="20" y2="38" />
      <line x1="14" y1="38" x2="26" y2="38" />
      {/* Wave bars (only when active) */}
      {isActive && (
        <>
          <line x1="4" y1="18" x2="4" y2="22" className="animate-[bounce_0.6s_infinite]" />
          <line x1="36" y1="18" x2="36" y2="22" className="animate-[bounce_0.6s_0.2s_infinite]" />
        </>
      )}
    </svg>
  );
}
