"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { parseChatEvents } from "@/lib/abyss-api";

export interface CommandFile {
  name: string;
  path: string;
  url: string;
}

export interface SessionStream {
  text: string;
  streaming: boolean;
  error: string | null;
  /**
   * Slash commands like ``/send`` emit a ``command_result`` SSE event
   * that carries a file payload alongside the text. The stream stores
   * the latest payload so the chat view can render a download chip
   * for the assistant reply. ``null`` after a regular streaming reply
   * so the chip from a previous slash command does not bleed over.
   */
  commandFile?: CommandFile | null;
}

export interface SendResult {
  text: string;
  commandFile?: CommandFile | null;
}

export interface MultiSessionStreamHandle {
  streams: Map<string, SessionStream>;
  send: (
    bot: string,
    sessionId: string,
    message: string,
    attachmentPaths?: string[],
    voiceMode?: boolean
  ) => Promise<SendResult>;
  cancel: (sessionId: string) => void;
  cancelAll: () => void;
}

const EMPTY_STREAM: SessionStream = {
  text: "",
  streaming: false,
  error: null,
  commandFile: null,
};

export function getSessionStream(
  streams: Map<string, SessionStream>,
  sessionId: string | null | undefined
): SessionStream {
  if (!sessionId) return EMPTY_STREAM;
  return streams.get(sessionId) ?? EMPTY_STREAM;
}

export function useMultiSessionChatStream(
  onChunk?: (sessionId: string, chunk: string) => void
): MultiSessionStreamHandle {
  const [streams, setStreams] = useState<Map<string, SessionStream>>(new Map());
  const controllersRef = useRef<Map<string, AbortController>>(new Map());

  const patchStream = useCallback(
    (sessionId: string, patch: Partial<SessionStream>) => {
      setStreams((prev) => {
        const next = new Map(prev);
        const current = prev.get(sessionId) ?? EMPTY_STREAM;
        next.set(sessionId, { ...current, ...patch });
        return next;
      });
    },
    []
  );

  const send = useCallback(
    async (
      bot: string,
      sessionId: string,
      message: string,
      attachmentPaths: string[] = [],
      voiceMode = false
    ) => {
      // Abort prior in-flight stream for THIS session only.
      controllersRef.current.get(sessionId)?.abort();

      const controller = new AbortController();
      controllersRef.current.set(sessionId, controller);

      patchStream(sessionId, {
        text: "",
        streaming: true,
        error: null,
        commandFile: null,
      });

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
        let commandFile: CommandFile | null = null;
        for await (const event of parseChatEvents(response.body)) {
          if (event.type === "chunk") {
            accumulated += event.text;
            patchStream(sessionId, { text: accumulated });
            onChunk?.(sessionId, event.text);
          } else if (event.type === "command_result") {
            // Slash commands emit a single ``command_result`` event
            // (no incremental chunks). Capture both the text and the
            // optional ``file`` payload — ``/send <filename>`` ships
            // download metadata that the chat view turns into a
            // tappable chip on the assistant reply.
            accumulated = event.text;
            commandFile = event.file ?? null;
            patchStream(sessionId, {
              text: accumulated,
              commandFile,
            });
            onChunk?.(sessionId, event.text);
          } else if (event.type === "error") {
            patchStream(sessionId, { error: event.message });
          } else if (event.type === "done") {
            accumulated = event.text || accumulated;
            patchStream(sessionId, { text: accumulated });
          }
        }
        return { text: accumulated, commandFile };
      } catch (caught) {
        if ((caught as { name?: string }).name === "AbortError") {
          return { text: "" };
        }
        const message =
          caught instanceof Error ? caught.message : String(caught);
        patchStream(sessionId, { error: message });
        return { text: "" };
      } finally {
        patchStream(sessionId, { streaming: false });
        if (controllersRef.current.get(sessionId) === controller) {
          controllersRef.current.delete(sessionId);
        }
      }
    },
    [onChunk, patchStream]
  );

  const cancel = useCallback(
    (sessionId: string) => {
      const controller = controllersRef.current.get(sessionId);
      if (controller) {
        controller.abort();
        controllersRef.current.delete(sessionId);
      }
      patchStream(sessionId, { streaming: false });
    },
    [patchStream]
  );

  const cancelAll = useCallback(() => {
    for (const controller of controllersRef.current.values()) {
      controller.abort();
    }
    controllersRef.current.clear();
    setStreams((prev) => {
      const next = new Map(prev);
      for (const [sessionId, stream] of prev) {
        if (stream.streaming) {
          next.set(sessionId, { ...stream, streaming: false });
        }
      }
      return next;
    });
  }, []);

  // Abort every in-flight stream when the host component unmounts.
  useEffect(() => {
    const controllers = controllersRef.current;
    return () => {
      for (const controller of controllers.values()) {
        controller.abort();
      }
      controllers.clear();
    };
  }, []);

  return { streams, send, cancel, cancelAll };
}
