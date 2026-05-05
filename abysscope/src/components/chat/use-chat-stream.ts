"use client";

import { useCallback, useRef, useState } from "react";
import { parseChatEvents } from "@/lib/abyss-api";

export interface StreamHandle {
  text: string;
  streaming: boolean;
  send: (
    bot: string,
    sessionId: string,
    message: string,
    attachmentPaths?: string[],
    voiceMode?: boolean
  ) => Promise<string>;
  cancel: () => void;
  error: string | null;
}

export function useChatStream(
  onChunk?: (chunk: string) => void
): StreamHandle {
  const [text, setText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (
      bot: string,
      sessionId: string,
      message: string,
      attachmentPaths: string[] = [],
      voiceMode = false
    ) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setText("");
      setError(null);
      setStreaming(true);

      try {
        const body: Record<string, unknown> = {
          bot,
          session_id: sessionId,
          message,
        };
        if (attachmentPaths.length > 0) {
          body.attachments = attachmentPaths;
        }
        if (voiceMode) {
          body.voice_mode = true;
        }
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: controller.signal,
        });
        if (!response.ok || !response.body) {
          const detail = await response.text();
          throw new Error(`chat failed: ${response.status} ${detail}`);
        }

        let accumulated = "";
        for await (const event of parseChatEvents(response.body)) {
          if (event.type === "chunk") {
            accumulated += event.text;
            setText(accumulated);
            onChunk?.(event.text);
          } else if (event.type === "error") {
            setError(event.message);
          } else if (event.type === "done") {
            accumulated = event.text || accumulated;
            setText(accumulated);
          }
        }
        return accumulated;
      } catch (caught) {
        if ((caught as { name?: string }).name === "AbortError") {
          return "";
        }
        setError(caught instanceof Error ? caught.message : String(caught));
        return "";
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [onChunk]
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  }, []);

  return { text, streaming, send, cancel, error };
}
