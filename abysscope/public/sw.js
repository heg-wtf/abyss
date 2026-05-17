/**
 * Abyss Service Worker.
 *
 * Two responsibilities:
 *
 *  1. Show notifications for Web Push events. The Python server posts
 *     a small JSON body ``{title, body, bot?, session_id?}`` and we
 *     hand it to ``self.registration.showNotification``.
 *
 *  2. When the user taps a notification, navigate the open tab — or a
 *     freshly-opened one — to the chat that produced it. We stash the
 *     target session in the ``push-nav`` Cache so ``use-web-push.ts``
 *     can read it once the page mounts (iOS Safari fires
 *     ``notificationclick`` after the ``focus`` event, which makes a
 *     same-tick ``postMessage`` race-prone).
 *
 * Kept intentionally tiny — heavier logic belongs in the React app.
 */

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

function tagFor(data) {
  // Chat replies are keyed by session; cron / heartbeat are keyed by
  // (kind, job_name). A unique tag per surface keeps repeated runs
  // collapsing onto a single notification rather than pushing the
  // previous payload off-screen across unrelated bots.
  if (data.kind === "cron" || data.kind === "heartbeat") {
    return `routine:${data.bot || "abyss"}:${data.kind}:${data.job_name || "default"}`;
  }
  if (data.session_id) {
    return `session:${data.bot || "abyss"}:${data.session_id}`;
  }
  return undefined;
}

self.addEventListener("push", (event) => {
  const data = event.data?.json() ?? {};
  const title = data.title || "Abyss";
  const tag = tagFor(data);
  const options = {
    body: data.body || "",
    icon: "/android-chrome-192x192.png",
    badge: "/favicon-32x32.png",
    tag,
    renotify: !!tag,
    data: {
      bot: data.bot || null,
      session_id: data.session_id || null,
      kind: data.kind || null,
      job_name: data.job_name || null,
    },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

const PUSH_NAV_CACHE = "push-nav";
const PUSH_NAV_KEY = "/_push-pending";

function targetPath({ bot, sessionId, kind, jobName }) {
  if (bot && (kind === "cron" || kind === "heartbeat") && jobName) {
    return `/mobile/routine/${bot}/${kind}/${jobName}`;
  }
  if (bot && sessionId) {
    return `/mobile/chat/${bot}/${sessionId}`;
  }
  return "/mobile";
}

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const {
    bot,
    session_id: sessionId,
    kind,
    job_name: jobName,
  } = event.notification.data || {};
  const nav = { bot, sessionId, kind, jobName };

  event.waitUntil(
    caches
      .open(PUSH_NAV_CACHE)
      .then((cache) =>
        cache.put(PUSH_NAV_KEY, new Response(JSON.stringify(nav))),
      )
      .then(() => self.clients.matchAll({ type: "window", includeUncontrolled: true }))
      .then((windows) => {
        for (const client of windows) {
          if (client.url.includes(self.location.origin)) {
            client.postMessage({ type: "notification-click", ...nav });
            return client.focus();
          }
        }
        return self.clients.openWindow(targetPath(nav));
      }),
  );
});

self.addEventListener("message", (event) => {
  // The page broadcasts ``clear-notifications`` when it becomes
  // visible, so old notifications do not pile up after the user has
  // already seen the content.
  if (event.data?.type === "clear-notifications") {
    event.waitUntil(
      self.registration.getNotifications().then((notifications) => {
        notifications.forEach((n) => n.close());
      }),
    );
    return;
  }

  // Selective dismiss — fires from ``markSessionRead`` /
  // ``markRoutineRead`` so only the just-read tag clears. The
  // ``clear-notifications`` path above remains for the visibility
  // catch-up sweep when the page returns to foreground.
  if (event.data?.type === "dismiss-notification" && event.data.tag) {
    const tag = event.data.tag;
    event.waitUntil(
      self.registration.getNotifications({ tag }).then((notifications) => {
        notifications.forEach((n) => n.close());
      }),
    );
  }
});
