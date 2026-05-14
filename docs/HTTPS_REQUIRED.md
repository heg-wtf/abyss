# HTTPS-required features

Browser secure-context restrictions that the mobile (`/mobile`) PWA
hits. Until the abysscope origin is served over HTTPS, every feature
in this list will silently fail on non-`localhost` clients — most
notably the phone over Tailscale.

`localhost` and `127.0.0.1` are exempt (counted as "potentially
trustworthy" origins by every modern browser), so the desktop dev
loop still works without TLS.

| Feature | API | Notes |
| --- | --- | --- |
| Web Push notifications | `Notification.requestPermission`, `serviceWorker.register`, `PushManager.subscribe` | Reports as `unsupported` in `PushToggle`. The dashboard already shows the diagnostic banner on the `/mobile` push dialog. |
| Voice dictation (mic) | `navigator.mediaDevices.getUserMedia({ audio: true })` | Throws `NotAllowedError` / `SecurityError`. Mic button looks tappable but starts no recording. ElevenLabs Scribe WebSocket relies on this. |
| TTS playback (voice replies) | WebAudio decode of streamed audio | Stream itself works over HTTP, but the playback handoff currently shares the same voice-mode pipeline that needs mic access — disable both together. |
| PWA install | `manifest.webmanifest` + service worker | iOS "Add to Home Screen" only registers a true standalone PWA when the page is served over HTTPS. On HTTP iOS still bookmarks the site but `standalone` display mode + push won't activate. |
| Service Worker scope | `serviceWorker.register('/sw.js')` | Browsers refuse to install service workers from non-secure origins, which knocks out push *and* the `PwaFreshness` BFCache reload heuristic. |
| Clipboard write (auto-copy / share sheets) | `navigator.clipboard.writeText` | Falls back to user-selection mode silently. We don't depend on this today but any future "copy reply" / "share" button will hit it. |
| Camera (future image input) | `navigator.mediaDevices.getUserMedia({ video: true })` | Not used today; flagged here so we don't ship an attach-from-camera button without TLS in place. |

## Recommended path forward

Tailscale Serve with `--https=443` lands an automatic Let's Encrypt
cert on `<host>.<tailnet>.ts.net` and proxies into the local
abysscope port:

```bash
sudo tailscale serve --bg --https=443 --set-path=/ http://localhost:3847
```

After that the iPhone reaches the dashboard at
`https://<host>.<tailnet>.ts.net/mobile` and every API in the table
above starts answering. Push subscription, mic, and PWA install all
become real once that's in place.

## How to verify quickly

Open the `/mobile` push dialog on the device. If status flips from
`unsupported` to `permission-prompt` or `subscribed`, the origin
finally qualifies as secure and the rest of the list (mic, PWA
install, clipboard) becomes available in the same session.
