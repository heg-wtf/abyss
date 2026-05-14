"use client";

import * as React from "react";
import { useWebPush } from "@/hooks/use-web-push";

/**
 * Single ``useWebPush`` instance hoisted to the root layout so
 * notification-click routing + visibility tracking run on *every*
 * page, not just the surface that happened to mount the hook (the
 * earlier ``PushToggle``-only mounting was the codex P1/P2 review
 * comment on PR #51 — a notification fired while the user was on
 * ``/chat`` or ``/mobile/chat/...`` would land but the click could
 * not route them anywhere because no listener was registered).
 *
 * Consumers pull subscribe / enable / disable state through
 * ``useWebPushContext`` instead of calling ``useWebPush`` again,
 * which would create a second instance and double-fire visibility
 * pings + notification-click listeners.
 */

type WebPushHandle = ReturnType<typeof useWebPush>;

const WebPushContext = React.createContext<WebPushHandle | null>(null);

export function WebPushProvider({ children }: { children: React.ReactNode }) {
  const push = useWebPush();
  return (
    <WebPushContext.Provider value={push}>{children}</WebPushContext.Provider>
  );
}

export function useWebPushContext(): WebPushHandle {
  const value = React.useContext(WebPushContext);
  if (!value) {
    throw new Error(
      "useWebPushContext must be called inside <WebPushProvider>",
    );
  }
  return value;
}
