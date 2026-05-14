"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

/**
 * Push subscription + visibility plumbing for the dashboard.
 *
 * Two responsibilities, both kept inside this hook so individual
 * components don't repeatedly poke at the Service Worker:
 *
 *   1. **Subscription lifecycle.** ``enable()`` requests notification
 *      permission, registers ``/sw.js``, subscribes via
 *      ``pushManager.subscribe``, and POSTs the result to the
 *      sidecar. ``disable()`` unsubscribes locally + DELETE on the
 *      server. Both are idempotent.
 *
 *   2. **Visibility ping.** While the page is focused we tell the
 *      server "skip my device" so the SW doesn't fire a notification
 *      for content I'm already looking at. On blur / unload we send
 *      ``visible: false`` with ``keepalive`` so the next push can
 *      reach the device.
 *
 * iOS Safari requires the page be installed as a PWA before
 * Notification API calls are even allowed — we let the caller check
 * for that and surface a banner in the UI; this hook just no-ops if
 * the platform refuses.
 */

const DEVICE_ID_STORAGE_KEY = "abyss.push.deviceId";
const PUSH_NAV_CACHE = "push-nav";
const PUSH_NAV_KEY = "/_push-pending";

export type PushStatus =
  | "unsupported"
  | "permission-default"
  | "permission-denied"
  | "permission-granted"
  | "subscribed";

interface NavParams {
  bot?: string | null;
  sessionId?: string | null;
}

function getDeviceId(): string {
  let id = localStorage.getItem(DEVICE_ID_STORAGE_KEY);
  if (!id) {
    id =
      typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem(DEVICE_ID_STORAGE_KEY, id);
  }
  return id;
}

function isPushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

function urlBase64ToUint8Array(base64String: string): ArrayBuffer {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) output[i] = raw.charCodeAt(i);
  // ``PushManager.subscribe`` wants ``BufferSource``. Casting to a
  // plain ``ArrayBuffer`` avoids the ``Uint8Array<ArrayBufferLike>``
  // typing mismatch that Next 16 / TS 5.x picks up.
  return output.buffer as ArrayBuffer;
}

async function consumePushNav(): Promise<NavParams | null> {
  try {
    if (typeof caches === "undefined") return null;
    const cache = await caches.open(PUSH_NAV_CACHE);
    const res = await cache.match(PUSH_NAV_KEY);
    if (!res) return null;
    await cache.delete(PUSH_NAV_KEY);
    return (await res.json()) as NavParams;
  } catch {
    return null;
  }
}

interface UseWebPushOptions {
  /** Suppress automatic visibility pings — useful for unit tests. */
  disableVisibilityTracking?: boolean;
}

export function useWebPush(options: UseWebPushOptions = {}) {
  const router = useRouter();
  const [status, setStatus] = React.useState<PushStatus>("unsupported");
  const [error, setError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);

  const refresh = React.useCallback(async () => {
    if (!isPushSupported()) {
      setStatus("unsupported");
      return;
    }
    const permission = Notification.permission;
    if (permission === "denied") {
      setStatus("permission-denied");
      return;
    }
    if (permission === "default") {
      setStatus("permission-default");
      return;
    }
    try {
      const registration = await navigator.serviceWorker.ready;
      const sub = await registration.pushManager.getSubscription();
      setStatus(sub ? "subscribed" : "permission-granted");
    } catch {
      setStatus("permission-granted");
    }
  }, []);

  // First render: register the SW once and then sync status.
  React.useEffect(() => {
    if (!isPushSupported()) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Service worker registration can fail on insecure origins
      // (http://, except localhost). Surface as ``unsupported`` so
      // the UI shows the HTTPS hint.
      setStatus("unsupported");
    });
    refresh();
  }, [refresh]);

  // Listen for notification clicks broadcast by the SW.
  React.useEffect(() => {
    if (!isPushSupported()) return;
    const handle = (event: MessageEvent) => {
      const data = event.data;
      if (data?.type !== "notification-click") return;
      const bot = (data.bot as string | null) ?? null;
      const sessionId = (data.sessionId as string | null) ?? null;
      if (bot && sessionId) {
        router.push(`/mobile/chat/${bot}/${sessionId}`);
      } else {
        router.push("/mobile");
      }
    };
    navigator.serviceWorker.addEventListener("message", handle);
    // The SW caches the navigation target so iOS Safari's
    // ``notificationclick``-after-focus ordering does not lose the
    // intent. Drain the cache on mount + focus.
    const drain = async () => {
      const nav = await consumePushNav();
      if (!nav) return;
      if (nav.bot && nav.sessionId) {
        router.push(`/mobile/chat/${nav.bot}/${nav.sessionId}`);
      }
    };
    drain();
    const onFocus = () => {
      drain();
      // Also clear any sticky notifications now that the user is back.
      navigator.serviceWorker.ready.then((reg) => {
        reg.active?.postMessage({ type: "clear-notifications" });
      });
    };
    window.addEventListener("focus", onFocus);
    window.addEventListener("pageshow", onFocus);
    return () => {
      navigator.serviceWorker.removeEventListener("message", handle);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("pageshow", onFocus);
    };
  }, [router]);

  // Visibility ping (focus / blur / 30s heartbeat while focused).
  React.useEffect(() => {
    if (options.disableVisibilityTracking) return;
    if (typeof window === "undefined") return;

    const send = (visible: boolean) => {
      const deviceId = (() => {
        try {
          return getDeviceId();
        } catch {
          return null;
        }
      })();
      if (!deviceId) return;
      fetch("/api/push/visibility", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deviceId, visible }),
        keepalive: true,
      }).catch(() => {});
    };

    send(document.hasFocus());
    const onFocus = () => send(true);
    const onBlur = () => send(false);
    window.addEventListener("focus", onFocus);
    window.addEventListener("blur", onBlur);
    const beat = setInterval(() => {
      if (document.hasFocus()) send(true);
    }, 30_000);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("blur", onBlur);
      clearInterval(beat);
      send(false);
    };
  }, [options.disableVisibilityTracking]);

  const enable = React.useCallback(async () => {
    if (!isPushSupported()) {
      setError("This browser does not support Web Push.");
      return;
    }
    setError(null);
    setPending(true);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setStatus(
          permission === "denied" ? "permission-denied" : "permission-default",
        );
        setError(
          permission === "denied"
            ? "Notifications blocked. Re-enable in browser settings."
            : "Permission was not granted.",
        );
        return;
      }
      const registration = await navigator.serviceWorker.ready;
      let subscription = await registration.pushManager.getSubscription();
      if (!subscription) {
        const vapidResponse = await fetch("/api/push/vapid-key");
        if (!vapidResponse.ok) {
          throw new Error("Failed to fetch VAPID key");
        }
        const { publicKey } = (await vapidResponse.json()) as {
          publicKey: string;
        };
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(publicKey),
        });
      }
      const payload = {
        ...subscription.toJSON(),
        device_id: getDeviceId(),
      };
      const response = await fetch("/api/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(`subscribe failed: ${response.status}`);
      }
      setStatus("subscribed");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      await refresh();
    } finally {
      setPending(false);
    }
  }, [refresh]);

  const disable = React.useCallback(async () => {
    if (!isPushSupported()) return;
    setError(null);
    setPending(true);
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      if (subscription) {
        const endpoint = subscription.endpoint;
        await subscription.unsubscribe().catch(() => {});
        await fetch("/api/push/subscribe", {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint }),
        }).catch(() => {});
      }
      setStatus("permission-granted");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setPending(false);
    }
  }, []);

  return {
    status,
    error,
    pending,
    enable,
    disable,
    refresh,
  };
}
