"use client";

import * as React from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BotAvatar } from "@/components/bot-avatar";
import { Orb, type AgentState } from "@/components/ui/orb";
import type { VoiceState } from "./use-voice-mode";

interface Props {
  botName: string;
  botDisplayName: string;
  voiceState: VoiceState;
  partialTranscript: string;
  error: string | null;
  onClose: () => void;
}

const STATE_LABEL: Record<VoiceState, string> = {
  idle: "",
  recording: "듣는 중...",
  processing: "처리 중...",
  speaking: "응답 중...",
};

function toAgentState(state: VoiceState): AgentState {
  if (state === "recording") return "listening";
  if (state === "processing") return "thinking";
  if (state === "speaking") return "talking";
  return null;
}

export function VoiceScreen({ botName, botDisplayName, voiceState, partialTranscript, error, onClose }: Props) {
  return (
    <div className="flex h-full flex-col items-center justify-between bg-background px-6 py-8">
      {/* Header */}
      <div className="flex w-full items-center justify-between">
        <div className="flex items-center gap-3">
          <BotAvatar botName={botName} displayName={botDisplayName} size="sm" />
          <span className="text-sm font-medium">{botDisplayName}</span>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="음성 모드 종료">
          <X className="size-5" />
        </Button>
      </div>

      {/* Orb */}
      <div className="size-56">
        <Orb agentState={toAgentState(voiceState)} />
      </div>

      {/* Status + partial transcript */}
      <div className="flex flex-col items-center gap-1 text-center">
        <p className="text-sm text-muted-foreground">
          {error ? <span className="text-destructive">{error}</span> : STATE_LABEL[voiceState]}
        </p>
        {partialTranscript && voiceState === "recording" && (
          <p className="max-w-xs text-sm text-foreground/70 italic">{partialTranscript}</p>
        )}
      </div>
    </div>
  );
}
