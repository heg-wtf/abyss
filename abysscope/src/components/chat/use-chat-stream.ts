"use client";

import { useSyncExternalStore } from "react";
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

// ---------------------------------------------------------------------------
// Module-level store
//
// Streaming state lives outside the React tree so it survives navigation.
// Without this, leaving and re-entering a chat surface unmounted the hook,
// cancelled every AbortController, and showed a stale "no streaming" UI even
// while the backend was still generating the reply.
//
// ``useSyncExternalStore`` is the standard React 18 pattern for adapting an
// imperative store to a component subscription. We bump ``version`` whenever
// the map mutates and use that as the snapshot identity so React can compare
// cheaply without copying the Map every patch.
// ---------------------------------------------------------------------------

const streamMap = new Map<string, SessionStream>();
const controllerMap = new Map<string, AbortController>();
const subscribers = new Set<() => void>();
let version = 0;

function notify() {
  version += 1;
  for (const subscriber of subscribers) subscriber();
}

function getVersion() {
  return version;
}

function subscribe(callback: () => void) {
  subscribers.add(callback);
  return () => {
    subscribers.delete(callback);
  };
}

function patchStream(sessionId: string, patch: Partial<SessionStream>) {
  const current = streamMap.get(sessionId) ?? EMPTY_STREAM;
  streamMap.set(sessionId, { ...current, ...patch });
  notify();
}

async function send(
  bot: string,
  sessionId: string,
  message: string,
  attachmentPaths: string[] = [],
  voiceMode = false
): Promise<SendResult> {
  // Abort prior in-flight stream for THIS session only.
  controllerMap.get(sessionId)?.abort();

  const controller = new AbortController();
  controllerMap.set(sessionId, controller);

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
      } else if (event.type === "command_result") {
        // Slash commands emit a single ``command_result`` event
        // (no incremental chunks). Capture both the text and the
        // optional ``file`` payload — ``/send <filename>`` ships
        // download metadata that the chat view turns into a
        // tappable chip on the assistant reply.
        accumulated = event.text;
        commandFile = event.file ?? null;
        patchStream(sessionId, { text: accumulated, commandFile });
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
    if (controllerMap.get(sessionId) === controller) {
      controllerMap.delete(sessionId);
    }
  }
}

function cancel(sessionId: string) {
  const controller = controllerMap.get(sessionId);
  if (controller) {
    controller.abort();
    controllerMap.delete(sessionId);
  }
  patchStream(sessionId, { streaming: false });
}

function cancelAll() {
  for (const controller of controllerMap.values()) {
    controller.abort();
  }
  controllerMap.clear();
  let dirty = false;
  for (const [sessionId, stream] of streamMap.entries()) {
    if (stream.streaming) {
      streamMap.set(sessionId, { ...stream, streaming: false });
      dirty = true;
    }
  }
  if (dirty) notify();
}

export function useMultiSessionChatStream(): MultiSessionStreamHandle {
  // Subscribe to store changes; the snapshot identity (``version``) ticks
  // whenever the map mutates so React re-renders. Returning the map itself
  // would not work because we mutate it in place to keep referential equality
  // for cheap ``streams.get(id)`` reads outside React.
  useSyncExternalStore(subscribe, getVersion, getVersion);
  return {
    streams: streamMap,
    send,
    cancel,
    cancelAll,
  };
}
