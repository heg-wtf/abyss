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

### 4. HTTPS (optional, recommended later)

The Phase 1 mobile shell does **not** require HTTPS — slash commands,
attachments, and chat streaming all work over plain HTTP on Tailscale.

When PWA / Web Push lands (next plan), iOS will require HTTPS for
service worker registration. Use `tailscale serve` to obtain a free
HTTPS cert for the tailnet hostname:

```bash
tailscale serve https / http://localhost:3847
```

Then visit `https://macbook.your-tailnet.ts.net/mobile`.

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
| `/mobile`                              | Redirects to `/mobile/sessions`. |
| `/mobile/sessions`                     | List of chats across every bot. Custom names, last-message preview, relative timestamps, long-press → rename / delete, top-right `New` button opens a bot picker. |
| `/mobile/chat/<bot>/<sessionId>`       | Single chat: header (hamburger → sessions, bot name, workspace files), message list, fixed input bar with `[slash] [attach] [textarea] [voice/send]`. Slash commands route through the same `abyss.commands` backend used by the Telegram bot, so `/cron list`, `/help`, `/files`, etc. all work. |

The desktop UI at `/chat` continues to work unchanged.

## Future work (separate plans)

- PWA `manifest.json` + service worker so the page can be installed on
  the iOS / Android home screen.
- VAPID keys + Web Push so the bot can notify the phone when an
  assistant reply lands or a cron job completes.
- Voice mode parity with the desktop `/chat` page.
