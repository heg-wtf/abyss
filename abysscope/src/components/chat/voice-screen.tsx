"use client";

import * as React from "react";
import { X } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { Orb, type AgentState } from "@/components/ui/orb";
import type { VoiceState } from "./use-voice-mode";

interface Props {
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

export function VoiceScreen({ botDisplayName, voiceState, partialTranscript, error, onClose }: Props) {
  const { resolvedTheme } = useTheme();
  const orbColors: [string, string] = resolvedTheme === "dark"
    ? ["#cccccc", "#ffffff"]
    : ["#111111", "#2a2a2a"];

  return (
    <div className="flex h-full flex-col items-center justify-between bg-background px-4 py-5">
      <div className="flex w-full items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">{botDisplayName}</span>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="음성 모드 종료">
          <X className="size-4" />
        </Button>
      </div>

      <div className="size-44">
        <Orb agentState={toAgentState(voiceState)} colors={orbColors} />
      </div>

      <div className="flex flex-col items-center gap-1 px-2 text-center">
        <p className="text-sm text-muted-foreground">
          {error ? <span className="text-destructive">{error}</span> : STATE_LABEL[voiceState]}
        </p>
        {partialTranscript && voiceState === "recording" && (
          <p className="text-sm text-foreground/70 italic">{partialTranscript}</p>
        )}
      </div>
    </div>
  );
}
