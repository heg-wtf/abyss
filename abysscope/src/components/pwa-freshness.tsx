"use client";

import * as React from "react";

/**
 * Keep the PWA fresh across iOS background/foreground cycles.
 *
 * iOS Safari restores the standalone PWA from BFCache when the user
 * swipes back to the app — the page snapshot reappears without
 * re-executing JS, so any backend / build changes since the snapshot
 * never reach the screen. The symptom the user reported: "PWA에
 * 반영이 느리다."
 *
 * Two triggers force a network reload:
 *
 *   1. ``pageshow`` with ``event.persisted === true`` — the browser
 *      tells us explicitly that we just got restored from BFCache.
 *   2. ``visibilitychange`` to ``visible`` after the tab has been
 *      hidden for more than ``STALE_MS`` (5 minutes). Some restore
 *      paths fire ``pageshow`` with ``persisted=false`` but still
 *      hand us a stale module graph; this catches that.
 *
 * Inactive / brief tab switches stay snappy because we only reload
 * after the stale threshold, not on every focus.
 */

const STALE_MS = 5 * 60 * 1000;

export function PwaFreshness() {
  React.useEffect(() => {
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) window.location.reload();
    };
    let hiddenAt: number | null = null;
    const onVisibility = () => {
      if (document.visibilityState === "hidden") {
        hiddenAt = Date.now();
        return;
      }
      if (hiddenAt && Date.now() - hiddenAt > STALE_MS) {
        window.location.reload();
      }
      hiddenAt = null;
    };
    window.addEventListener("pageshow", onPageShow);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("pageshow", onPageShow);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return null;
}
