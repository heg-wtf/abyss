import * as React from "react";

/**
 * Detect touch-only input devices via the standard CSS media query.
 *
 * ``(hover: none) and (pointer: coarse)`` matches phones / tablets but
 * not a laptop with a touchscreen + keyboard (which reports
 * ``hover: hover``). The result starts ``false`` so SSR stays
 * deterministic; the actual value lands on first paint via the
 * ``useEffect`` below. ``addEventListener('change', ...)`` keeps the
 * value live if the user docks an external keyboard mid-session.
 */
export function useIsTouchDevice() {
  const [isTouch, setIsTouch] = React.useState(false);
  React.useEffect(() => {
    const query = window.matchMedia("(hover: none) and (pointer: coarse)");
    const update = () => setIsTouch(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return isTouch;
}
