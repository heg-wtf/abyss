"use client";

import * as React from "react";

/**
 * Minimal logo splash for cold page loads.
 *
 * Renders a full-screen dark overlay with the app logo centered.
 * Holds 1.2 s, fades out 0.3 s (total ~1.5 s) and unmounts. Honors
 * ``prefers-reduced-motion``.
 *
 * Implementation notes (revisited 2026-05-15):
 *   - **No CSS keyframes.** Earlier revisions used ``@keyframes
 *     logo-splash-bg / -logo`` in ``globals.css``. On iOS PWA cold
 *     starts the browser would render the SSR HTML for one frame
 *     before the bundled stylesheet (with the keyframes + the
 *     ``--background`` token) arrived, briefly revealing the chat
 *     content beneath the still-transparent overlay. We now drive
 *     the fade with a state machine + inline ``transition: opacity``
 *     so the first paint already has ``opacity: 1`` baked in.
 *   - **No ``next/image``.** Plain ``<img>`` so there's no
 *     placeholder swap mid-animation.
 *   - **Inline color.** Background uses the same ``#131313`` the
 *     PWA manifest does for the OS splash, so the hand-off between
 *     the system-rendered splash and our overlay is seamless.
 */

type Phase = "showing" | "fading-out" | "done";

interface LogoSplashProps {
  onComplete: () => void;
}

const HOLD_MS = 1200;
const FADE_MS = 300;

export function LogoSplash({ onComplete }: LogoSplashProps) {
  const [phase, setPhase] = React.useState<Phase>("showing");
  const completedRef = React.useRef(false);

  const finish = React.useCallback(() => {
    if (completedRef.current) return;
    completedRef.current = true;
    onComplete();
  }, [onComplete]);

  React.useEffect(() => {
    // Reduced-motion users skip the animation entirely.
    if (
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      const id = window.setTimeout(finish, 50);
      return () => window.clearTimeout(id);
    }

    const fadeTimer = window.setTimeout(
      () => setPhase("fading-out"),
      HOLD_MS,
    );
    // Safety: if ``onTransitionEnd`` never fires (e.g. element
    // detached mid-transition), still complete after the full
    // expected lifetime + a small margin.
    const fallback = window.setTimeout(finish, HOLD_MS + FADE_MS + 100);
    return () => {
      window.clearTimeout(fadeTimer);
      window.clearTimeout(fallback);
    };
  }, [finish]);

  if (phase === "done") return null;

  const fading = phase === "fading-out";

  return (
    <div
      role="presentation"
      aria-hidden
      onTransitionEnd={(event) => {
        // Only react when the OUTER ``opacity`` transition ends —
        // the inner ``<img>`` doesn't currently animate, but guard
        // against future changes.
        if (event.target !== event.currentTarget) return;
        if (fading) finish();
      }}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "#131313",
        opacity: fading ? 0 : 1,
        transition: `opacity ${FADE_MS}ms ease-in-out`,
        pointerEvents: "none",
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- plain
          <img> keeps the splash free of next/image placeholder
          swapping mid-animation. */}
      <img
        src="/logo-square.png"
        alt=""
        width={160}
        height={160}
        style={{ width: 160, height: 160 }}
      />
    </div>
  );
}
