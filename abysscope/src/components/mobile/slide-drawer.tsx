"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface Props {
  /** Which edge the drawer slides in from. */
  side: "left" | "right";
  open: boolean;
  onClose: () => void;
  /** Width of the drawer panel; defaults to 85vw with a sane cap. */
  className?: string;
  children: React.ReactNode;
  /**
   * Override the default ``aria-label`` of the dim backdrop. Used by
   * a11y when the panel itself does not announce its purpose.
   */
  backdropLabel?: string;
}

/**
 * Mobile slide-in drawer.
 *
 * The chat screen used to navigate away from itself for sessions /
 * workspace; the user asked for a "drawer pushes the chat aside"
 * pattern instead. We use ``position: fixed`` over the whole viewport
 * with a translucent backdrop and a transform-based slide so the
 * chat behind stays visible — tapping it closes the drawer, the chat
 * picks up exactly where the user left it.
 *
 * Pure CSS transitions, no vaul dependency. Keyboard ``Esc`` closes,
 * the panel takes focus on open so screen readers announce it.
 */
export function SlideDrawer({
  side,
  open,
  onClose,
  className,
  children,
  backdropLabel,
}: Props) {
  const panelRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    // Focus the panel so VoiceOver / TalkBack announce it.
    panelRef.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // While the drawer is closed we keep the DOM mounted at
  // ``pointer-events: none`` so the transform transition runs even
  // on the very first open. Without that the panel would pop in.
  return (
    <div
      className={cn(
        "fixed inset-0 z-40",
        open ? "pointer-events-auto" : "pointer-events-none",
      )}
      aria-hidden={!open}
    >
      <button
        type="button"
        onClick={onClose}
        aria-label={backdropLabel ?? "Close drawer"}
        tabIndex={open ? 0 : -1}
        className={cn(
          "absolute inset-0 cursor-default bg-black/40 transition-opacity duration-200",
          open ? "opacity-100" : "opacity-0",
        )}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        className={cn(
          "absolute inset-y-0 flex w-[85vw] max-w-sm flex-col bg-background shadow-xl outline-none transition-transform duration-200 ease-out",
          side === "left" ? "left-0" : "right-0",
          open
            ? "translate-x-0"
            : side === "left"
              ? "-translate-x-full"
              : "translate-x-full",
          className,
        )}
        style={{
          paddingTop: "env(safe-area-inset-top)",
          paddingBottom: "env(safe-area-inset-bottom)",
        }}
      >
        {children}
      </div>
    </div>
  );
}
