# Mobile access (`/mobile`)

abyss runs on your Mac. The dashboard at port 3847 hosts a mobile route
at **`http://<host>:3847/mobile`** that turns abysscope into a chat
client you can use from a phone or tablet.

Phase 1 only ships the UI shell — there is no PWA manifest, no service
worker, and no Web Push yet. The mobile UI is still usable from any
modern browser; this document explains the recommended access pattern.

## Recommended setup: Tailscale

Tailscale is the simplest way to reach your Mac from a phone over the
internet without exposing port 3847 publicly. The same trick is what
purplemux recommends for the same scenario.

### 1. Install Tailscale

- Mac (server): https://tailscale.com/download — install + sign in.
- Phone (client): App Store / Play Store — sign in to the same account.

### 2. Start the dashboard

```bash
abyss dashboard start
```

By default the dashboard binds to loopback only. Bind to all interfaces
so Tailscale clients can reach it:

```bash
ABYSS_DASHBOARD_HOST=0.0.0.0 abyss dashboard start
```

(You can still keep the dashboard process foreground; `--daemon` works
the same way.)

### 3. Find your Tailscale hostname

```bash
tailscale ip -4
# or look up the device name in the Tailscale app
```

If your Mac shows up as `macbook` in Tailscale, the dashboard URL on
your phone is

```
http://macbook.your-tailnet.ts.net:3847/mobile
```

iOS Safari + Android Chrome both accept this URL over the Tailscale VPN
without a public DNS record.

### 4. HTTPS for PWA install + Web Push

Once PWA install + Web Push are wired in (see *PWA install* and
*Notifications* below), iOS Safari refuses to register a Service
Worker over plain HTTP, so the dashboard needs an HTTPS origin.
``tailscale serve`` is the simplest way to get one — Tailscale issues
a free Let's Encrypt cert for the tailnet hostname:

```bash
tailscale serve https / http://localhost:3847
```

Then visit `https://macbook.your-tailnet.ts.net/mobile` on the phone.
The HTTP URL keeps working for development.

## PWA install

1. Open the HTTPS dashboard URL in **iOS Safari** (16.4+).
2. Tap **Share → Add to Home Screen**.
3. Confirm the name (default "Abyss") and tap **Add**.
4. Open the icon from the home screen — the browser chrome
   disappears, the page runs full-screen, and a Service Worker
   registers in the background.

On **Android Chrome**, an "Install app" banner appears automatically
after the manifest is detected; tap it (or use the ⋮ menu →
**Install app**). The Service Worker registers immediately because
Android does not require home-screen install for it.

## Notifications

The dashboard sends a Web Push notification when a bot replies, a
cron job finishes, or a heartbeat reports something worth looking
at. Tabs currently focused on the dashboard are skipped so you
don't get double-notified.

1. Install the PWA (above).
2. Open the PWA, tap the **bell** icon in the top-right of
   ``/mobile``.
3. Tap **Enable**. iOS / Android will ask for notification
   permission — allow it.
4. The bell turns solid; future replies arrive as native
   notifications. Tap a notification to jump straight to that
   chat.

To stop receiving pushes, open the same sheet and tap **Disable**.
Or remove the PWA from the home screen — abyss will purge the
subscription on the next failed delivery.

### VAPID key backup

The server's identity for Web Push lives at
``~/.abyss/vapid-keys.json`` (mode 0600). Deleting that file
invalidates **every** existing browser subscription — back it up
alongside ``config.yaml`` if you rebuild the Mac.

## Alternative: same Wi-Fi only

If both devices are on your home network you can skip Tailscale entirely:

```bash
ipconfig getifaddr en0          # find the Mac's LAN IP, e.g. 192.168.1.42
ABYSS_DASHBOARD_HOST=0.0.0.0 abyss dashboard start
```

On the phone, open `http://192.168.1.42:3847/mobile`. This breaks the
moment either device leaves the network, so Tailscale is preferable.

## What's on `/mobile`

| Route | What it shows |
|-------|---------------|
| `/mobile`                              | List of chats across every bot. Custom names, last-message preview, relative timestamps, long-press → rename / delete, top-right `New` button opens a bot picker. (``/mobile/sessions`` redirects here for backward compatibility.) |
| `/mobile/chat/<bot>/<sessionId>`       | Single chat: header (hamburger → sessions, bot name, workspace files), message list, fixed input bar with `[slash] [attach] [textarea] [voice/send]`. Slash commands route through the same `abyss.commands` backend used by the Telegram bot, so `/cron list`, `/help`, `/files`, etc. all work. |

The desktop UI at `/chat` continues to work unchanged.

## Future work (separate plans)

- PWA `manifest.json` + service worker so the page can be installed on
  the iOS / Android home screen.
- VAPID keys + Web Push so the bot can notify the phone when an
  assistant reply lands or a cron job completes.
- Voice mode parity with the desktop `/chat` page.
