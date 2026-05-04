"use client";

import * as React from "react";
import { Mic, MicOff, Square, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useVoicePipeline } from "@/hooks/use-voice-pipeline";
import { SentenceChunker } from "@/lib/sentence-chunker";
import { listVoiceProfiles, type VoiceProfile } from "@/lib/voicebox";
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
  const [profiles, setProfiles] = React.useState<VoiceProfile[]>([]);
  const [selectedProfileId, setSelectedProfileId] = React.useState<string | null>(
    null
  );
  const [profilesLoading, setProfilesLoading] = React.useState(true);
  const [profilesError, setProfilesError] = React.useState<string | null>(null);
  // Snapshot the streaming text length at mount so we don't re-speak
  // anything the LLM had already produced before voice mode was entered.
  const lastSpokenLenRef = React.useRef(streamingText.length);
  const streamCompleteRef = React.useRef(true);
  const chunkerRef = React.useRef<SentenceChunker | null>(null);
  if (chunkerRef.current === null) {
    chunkerRef.current = new SentenceChunker();
  }

  // Load voice profiles on mount.
  React.useEffect(() => {
    let cancelled = false;
    setProfilesLoading(true);
    void (async () => {
      try {
        const list = await listVoiceProfiles();
        if (cancelled) return;
        setProfiles(list);
        setSelectedProfileId(list[0]?.id ?? null);
        setProfilesError(null);
      } catch (err) {
        if (cancelled) return;
        setProfilesError(
          err instanceof Error ? err.message : "프로필 로드 실패"
        );
      } finally {
        if (!cancelled) setProfilesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

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
    profileId: selectedProfileId,
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

  const noProfileAvailable =
    !profilesLoading && profiles.length === 0;

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6 py-8">
      <div className="flex w-full items-center justify-between gap-2">
        {profiles.length > 1 ? (
          <select
            value={selectedProfileId ?? ""}
            onChange={(event) => setSelectedProfileId(event.target.value || null)}
            className="rounded-md border bg-background px-2 py-1 text-xs"
            aria-label="음성 프로필 선택"
          >
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.name}
              </option>
            ))}
          </select>
        ) : (
          <span className="text-xs text-muted-foreground">
            {profilesLoading
              ? "프로필 로딩 중…"
              : profiles.length === 1
                ? `프로필: ${profiles[0].name}`
                : "프로필 없음"}
          </span>
        )}
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

      {profilesError && (
        <div className="max-w-md text-center text-sm text-destructive">
          {profilesError}
        </div>
      )}

      {noProfileAvailable && (
        <div className="max-w-md text-center text-sm text-amber-600 dark:text-amber-400">
          Voicebox에 음성 프로필이 없습니다. Voicebox 앱에서 프로필을
          만든 뒤 다시 시도하세요.
        </div>
      )}

      {errorMessage && (
        <div className="max-w-md text-center text-sm text-destructive">
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
