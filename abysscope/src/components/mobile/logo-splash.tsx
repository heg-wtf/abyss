"use client";

import Image from "next/image";
import * as React from "react";

/**
 * Minimal logo splash for cold page loads.
 *
 * Renders a full-screen dark overlay with the app logo centered.
 * Fades in 0.3s → holds 0.9s → fades out 0.3s (total 1.5s) and then
 * calls ``onComplete`` so ``MobileShell`` can unmount it. Honors
 * ``prefers-reduced-motion``.
 *
 * Why ``MobileShell`` only mounts this on the *initial* render and
 * never on background↔foreground transitions: a hot resume keeps the
 * React tree mounted, so ``useState`` initial values don't run again
 * and ``visibilitychange`` is intentionally not wired here.
 */

interface LogoSplashProps {
  onComplete: () => void;
}

export function LogoSplash({ onComplete }: LogoSplashProps) {
  const completedRef = React.useRef(false);

  const complete = React.useCallback(() => {
    if (completedRef.current) return;
    completedRef.current = true;
    onComplete();
  }, [onComplete]);

  // Belt-and-suspenders: the CSS animation triggers ``onAnimationEnd``,
  // but if that event is swallowed (e.g. reduced-motion shortens the
  // keyframes to 0–100% opacity-0 and some engines skip the event) we
  // still complete on a timer.
  React.useEffect(() => {
    const id = window.setTimeout(complete, 1600);
    return () => window.clearTimeout(id);
  }, [complete]);

  return (
    <div
      className="pointer-events-none fixed inset-0 z-[100] flex items-center justify-center bg-background"
      role="presentation"
      aria-hidden
      onAnimationEnd={complete}
      style={{
        animation: "logo-splash 1.5s ease-in-out forwards",
      }}
    >
      <Image
        src="/logo-square.png"
        alt=""
        width={160}
        height={160}
        priority
        className="size-40"
      />
    </div>
  );
}
