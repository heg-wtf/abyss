"use client";

import * as React from "react";
import { X } from "lucide-react";

/**
 * Three bouncing dots used for both the assistant's "thinking" bubble
 * and the queued-message hint under user bubbles.
 *
 * UX rules:
 *   - Dots bounce in sequence regardless of elapsed time (always alive).
 *   - The "Ns" counter stays hidden for the first 3s so fast responses
 *     don't flash a stale number.
 *   - After 30s, the label changes to "Still thinking · Ns" so the user
 *     knows a long task is still progressing instead of silently stuck.
 *
 * The counter refreshes every 500ms (the cheap path) to keep the
 * sub-second feel without burning re-renders.
 */
export function StreamingDots({ inline = false }: { inline?: boolean }) {
  return (
    <span
      role="presentation"
      aria-hidden
      className={inline ? "inline-flex items-center gap-1" : "flex items-center gap-1"}
    >
      <span
        className="block h-1.5 w-1.5 rounded-full bg-current"
        style={{ animation: "stream-dot 1.2s ease-in-out infinite", animationDelay: "0ms" }}
      />
      <span
        className="block h-1.5 w-1.5 rounded-full bg-current"
        style={{ animation: "stream-dot 1.2s ease-in-out infinite", animationDelay: "160ms" }}
      />
      <span
        className="block h-1.5 w-1.5 rounded-full bg-current"
        style={{ animation: "stream-dot 1.2s ease-in-out infinite", animationDelay: "320ms" }}
      />
    </span>
  );
}

/**
 * Inline "✕" cancel button. Visually small (20 px) but a 44 px tap
 * region is provided via ``-m-3 p-3`` to meet the Apple HIG touch
 * target without bloating the layout.
 */
export function CancelStreamButton({ onCancel }: { onCancel: () => void }) {
  return (
    <button
      type="button"
      onClick={onCancel}
      aria-label="Stop generating reply"
      className="-m-3 inline-flex items-center justify-center rounded-full p-3 text-muted-foreground transition-colors hover:text-foreground active:text-foreground"
    >
      <span className="flex h-5 w-5 items-center justify-center rounded-full border border-current">
        <X className="h-3 w-3" aria-hidden />
      </span>
    </button>
  );
}

export function StreamProgress({
  streaming,
  hasText,
  onCancel,
}: {
  streaming: boolean;
  hasText: boolean;
  onCancel?: () => void;
}) {
  const [elapsed, setElapsed] = React.useState(0);
  React.useEffect(() => {
    if (!streaming) {
      setElapsed(0);
      return;
    }
    const startedAt = Date.now();
    setElapsed(0);
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 500);
    return () => clearInterval(id);
  }, [streaming]);

  if (!streaming) return null;

  // Empty bubble — dots carry the whole indicator and serve as the
  // placeholder for "reply on the way".
  if (!hasText) {
    const showLong = elapsed >= 30;
    return (
      <div className="flex items-center gap-2 py-0.5 text-muted-foreground">
        <StreamingDots inline />
        {showLong && (
          <span className="tabular-nums text-[11px]">Still thinking · {elapsed}s</span>
        )}
        {onCancel && <CancelStreamButton onCancel={onCancel} />}
      </div>
    );
  }

  // Streaming text is already rendering — show a subtle bottom-row
  // indicator that fades the counter in after a few seconds.
  const showElapsed = elapsed >= 3;
  const longRunning = elapsed >= 30;
  return (
    <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
      <StreamingDots inline />
      <span
        className={`tabular-nums transition-opacity duration-300 ${
          showElapsed ? "opacity-100" : "opacity-0"
        }`}
      >
        {longRunning ? `Still thinking · ${elapsed}s` : `${elapsed}s`}
      </span>
      {onCancel && <CancelStreamButton onCancel={onCancel} />}
    </div>
  );
}
