"use client";

import * as React from "react";
import { Mic, MicOff, Square, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useVoicePipeline } from "@/hooks/use-voice-pipeline";
import { SentenceChunker } from "@/lib/sentence-chunker";
import { VoiceOrbVoid } from "./voice-orb";

interface Props {
  /** Live streaming assistant text — used to feed sentence chunker. */
  streamingText: string;
  /** True while the LLM is actively streaming chunks. */
  isStreaming: boolean;
  /** Called when a finalized transcript is ready to submit to the LLM. */
  onTranscript: (text: string) => void;
  /** Leave voice mode (e.g. user clicked the X). */
  onExit: () => void;
  /** Optional placeholder hint when the orb is idle. */
  hint?: string;
}

export function VoiceMode({
  streamingText,
  isStreaming,
  onTranscript,
  onExit,
  hint,
}: Props) {
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const lastSpokenLenRef = React.useRef(0);
  const streamCompleteRef = React.useRef(true);
  const chunkerRef = React.useRef<SentenceChunker | null>(null);
  if (chunkerRef.current === null) {
    chunkerRef.current = new SentenceChunker();
  }

  const handleTranscript = React.useCallback(
    (text: string) => {
      lastSpokenLenRef.current = 0;
      streamCompleteRef.current = false;
      chunkerRef.current = new SentenceChunker();
      setErrorMessage(null);
      onTranscript(text);
    },
    [onTranscript]
  );

  const handleError = React.useCallback((error: Error) => {
    setErrorMessage(error.message);
  }, []);

  const pipeline = useVoicePipeline({
    onTranscript: handleTranscript,
    onError: handleError,
  });

  // Drain new streaming text → sentence chunker → speak queue.
  React.useEffect(() => {
    if (!streamingText) return;
    const previous = lastSpokenLenRef.current;
    if (streamingText.length <= previous) return;
    const chunk = streamingText.slice(previous);
    lastSpokenLenRef.current = streamingText.length;
    const sentences = chunkerRef.current!.push(chunk);
    sentences.forEach((sentence) => {
      pipeline.speak(sentence).catch(() => {
        /* surfaced via onError */
      });
    });
  }, [streamingText, pipeline]);

  // When LLM stream ends, flush any remaining buffered text.
  React.useEffect(() => {
    if (isStreaming) {
      streamCompleteRef.current = false;
      return;
    }
    if (streamCompleteRef.current) return;
    streamCompleteRef.current = true;
    const remaining = chunkerRef.current!.flush();
    remaining.forEach((sentence) => {
      pipeline.speak(sentence).catch(() => {
        /* surfaced via onError */
      });
    });
  }, [isStreaming, pipeline]);

  const handleToggleListen = React.useCallback(() => {
    if (pipeline.isActive) {
      pipeline.stop();
    } else {
      void pipeline.start();
    }
  }, [pipeline]);

  const handleExit = React.useCallback(() => {
    pipeline.stop();
    pipeline.silence();
    onExit();
  }, [pipeline, onExit]);

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6 py-8">
      <div className="flex w-full justify-end">
        <Button
          variant="ghost"
          size="sm"
          onClick={handleExit}
          aria-label="음성 모드 종료"
        >
          <X className="size-4" />
          <span className="ml-1 text-xs">텍스트로 돌아가기</span>
        </Button>
      </div>

      <VoiceOrbVoid
        state={pipeline.state}
        amplitude={pipeline.amplitude}
        size={280}
      />

      <div className="text-center text-sm text-muted-foreground">
        {pipeline.state === "idle" && (hint ?? "버튼을 눌러 말하기 시작")}
        {pipeline.state === "listening" && "듣고 있어요…"}
        {pipeline.state === "thinking" && "변환하는 중…"}
        {pipeline.state === "speaking" && "응답 중…"}
      </div>

      {errorMessage && (
        <div className="text-center text-sm text-destructive">
          {errorMessage}
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button
          size="lg"
          variant={pipeline.isActive ? "destructive" : "default"}
          onClick={handleToggleListen}
        >
          {pipeline.isActive ? (
            <>
              <MicOff className="size-4" /> 멈추기
            </>
          ) : (
            <>
              <Mic className="size-4" /> 말하기
            </>
          )}
        </Button>
        {pipeline.state === "speaking" && (
          <Button
            size="lg"
            variant="outline"
            onClick={() => pipeline.silence()}
            aria-label="재생 중단"
          >
            <Square className="size-4" /> 재생 중단
          </Button>
        )}
      </div>
    </div>
  );
}
