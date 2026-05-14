"use client";

import * as React from "react";

/**
 * Tracks ``window.visualViewport.height`` so layouts can shrink in
 * step with the iOS soft keyboard.
 *
 * Why this exists: ``100dvh`` does NOT account for the keyboard on
 * iOS Safari. The dvh unit shrinks only when retractable browser UI
 * (address bar) collapses — when the keyboard opens, the dvh
 * container stays full height and the keyboard simply paints over
 * its bottom. The browser then auto-scrolls so the focused field is
 * visible, exposing the off-screen portion of the container as a
 * blank strip between the input bar and the keyboard.
 *
 * Subscribing to ``visualViewport.resize`` gives us the actually
 * usable height (keyboard subtracted) and we apply it as inline
 * ``style.height`` on the mobile layout root. Returns ``null`` during
 * SSR / first paint so the layout can fall back to ``100dvh`` until
 * hydration completes.
 */
export interface VisualViewport {
  height: number;
  offsetTop: number;
}

export function useVisualViewport(): VisualViewport | null {
  const [state, setState] = React.useState<VisualViewport | null>(null);

  React.useEffect(() => {
    const vv = window.visualViewport;
    const update = () => {
      if (vv) {
        setState({ height: vv.height, offsetTop: vv.offsetTop });
      } else {
        setState({ height: window.innerHeight, offsetTop: 0 });
      }
    };
    update();

    // iOS PWA standalone occasionally only fires ``resize`` on
    // ``window``, not on ``visualViewport`` — listen on both so we
    // don't miss the keyboard opening.
    window.addEventListener("resize", update);
    vv?.addEventListener("resize", update);
    vv?.addEventListener("scroll", update);
    return () => {
      window.removeEventListener("resize", update);
      vv?.removeEventListener("resize", update);
      vv?.removeEventListener("scroll", update);
    };
  }, []);

  return state;
}

/** @deprecated use {@link useVisualViewport} */
export function useVisualViewportHeight(): number | null {
  const vp = useVisualViewport();
  return vp ? vp.height : null;
}
