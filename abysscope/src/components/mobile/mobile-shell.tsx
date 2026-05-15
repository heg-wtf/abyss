"use client";

import * as React from "react";
import { LaunchIntro } from "@/components/mobile/launch-intro";
import { useVisualViewport } from "@/hooks/use-visual-viewport-height";

const INTRO_STORAGE_KEY = "abyss_pwa_intro_seen";

/**
 * Client wrapper that fixes the mobile layout to the iOS visual
 * viewport.
 *
 * The layout used to rely on ``h-dvh`` alone. That works fine until
 * the soft keyboard opens — ``dvh`` ignores the keyboard so the
 * container stays full height and the browser scrolls just enough
 * to keep the focused input visible, leaving a tall blank strip
 * between the input bar and the keyboard. Mirroring
 * ``visualViewport.height`` here keeps the whole chat surface flush
 * with the keyboard.
 *
 * Falls back to ``100dvh`` before hydration so SSR markup still has
 * a sensible height.
 */
export function MobileShell({ children }: { children: React.ReactNode }) {
  const vp = useVisualViewport();

  // First-run launch animation. SSR renders ``intro = false`` so the
  // server markup never includes the canvas; the effect below flips
  // it on for clients that haven't seen the intro yet. ``true`` here
  // means "still showing".
  const [introVisible, setIntroVisible] = React.useState(false);
  React.useEffect(() => {
    try {
      if (window.localStorage.getItem(INTRO_STORAGE_KEY) !== "true") {
        setIntroVisible(true);
      }
    } catch {
      // localStorage can throw under private mode / quota — skip the
      // intro rather than crashing the shell.
    }
  }, []);

  const dismissIntro = React.useCallback(() => {
    setIntroVisible(false);
    try {
      window.localStorage.setItem(INTRO_STORAGE_KEY, "true");
    } catch {
      // Same private-mode concern; the user just sees the intro
      // again next launch.
    }
  }, []);

  // Pin html and body via ``position: fixed`` + lock overflow so iOS
  // cannot auto-scroll the document when the textarea gains focus.
  // Plain ``overflow: hidden`` is not enough on iOS Safari — the
  // native "scroll input into view" routine treats body as
  // scrollable anyway and exposes the chrome below the shell as a
  // tall blank strip. Fixing ``html`` + ``body`` themselves stops
  // iOS from finding anything to scroll.
  React.useEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    const prev = {
      htmlOverflow: html.style.overflow,
      htmlPosition: html.style.position,
      htmlHeight: html.style.height,
      htmlWidth: html.style.width,
      bodyOverflow: body.style.overflow,
      bodyPosition: body.style.position,
      bodyOverscroll: body.style.overscrollBehavior,
      bodyHeight: body.style.height,
      bodyWidth: body.style.width,
    };
    html.style.overflow = "hidden";
    html.style.position = "fixed";
    html.style.height = "100%";
    html.style.width = "100%";
    body.style.overflow = "hidden";
    body.style.position = "fixed";
    body.style.overscrollBehavior = "none";
    body.style.height = "100%";
    body.style.width = "100%";
    return () => {
      html.style.overflow = prev.htmlOverflow;
      html.style.position = prev.htmlPosition;
      html.style.height = prev.htmlHeight;
      html.style.width = prev.htmlWidth;
      body.style.overflow = prev.bodyOverflow;
      body.style.position = prev.bodyPosition;
      body.style.overscrollBehavior = prev.bodyOverscroll;
      body.style.height = prev.bodyHeight;
      body.style.width = prev.bodyWidth;
    };
  }, []);

  // Anchor the shell to the visual viewport using both ``top`` and
  // ``height``. iOS does not always keep ``visualViewport.offsetTop``
  // at 0 — when the document scrolls (e.g. native focus auto-scroll
  // that slips past our overflow lock), the visual viewport rides
  // along and ``offsetTop`` becomes positive. Mirroring that here
  // keeps the shell glued to the visible window so the input bar
  // sits flush against the keyboard regardless.
  const top = vp ? `${vp.offsetTop}px` : "0px";
  const height = vp ? `${vp.height}px` : "100dvh";
  return (
    <div
      className="fixed inset-x-0 z-10 flex flex-col bg-background text-foreground"
      style={{
        top,
        height,
        paddingTop: "env(safe-area-inset-top)",
        paddingBottom: "env(safe-area-inset-bottom)",
        paddingLeft: "env(safe-area-inset-left)",
        paddingRight: "env(safe-area-inset-right)",
      }}
    >
      {children}
      {introVisible && <LaunchIntro onComplete={dismissIntro} />}
    </div>
  );
}
