/**
 * Source-level regression guards for the `/mobile` route skeleton.
 *
 * Vitest runs in node env without a DOM, so these checks are
 * intentionally static — they assert the load-bearing snippets in the
 * mobile entry points still match the Phase 2 contract:
 *
 *   - the mobile layout reserves safe-area-inset padding,
 *   - the sidebar shorts out on `/mobile/*` routes,
 *   - the index page redirects to the sessions list,
 *   - the sessions page wires the Phase 2 placeholder screen.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..", "..", "..");

function read(relPath: string): string {
  return readFileSync(path.join(ROOT, relPath), "utf8");
}

describe("/mobile route skeleton", () => {
  it("layout delegates the viewport-fitting shell to MobileShell", () => {
    const layoutSource = read("app/mobile/layout.tsx");
    expect(layoutSource).toMatch(/MobileShell/);
    // The shell owns the viewport sizing now — assert the load-bearing
    // bits live there instead of the layout file. ``position: fixed``
    // pins the shell to the layout viewport; combined with locking
    // ``html`` / ``body`` overflow, iOS can no longer scroll the
    // document up when the soft keyboard opens (which used to expose
    // a tall blank strip below the input bar).
    const shellSource = read("components/mobile/mobile-shell.tsx");
    expect(shellSource).toMatch(/fixed inset-x-0 z-10/);
    // ``100dvh`` is the SSR fallback before ``visualViewport.height``
    // kicks in on the client.
    expect(shellSource).toMatch(/100dvh/);
    expect(shellSource).toMatch(/safe-area-inset-top/);
    expect(shellSource).toMatch(/safe-area-inset-bottom/);
    expect(shellSource).toMatch(/html\.style\.overflow = "hidden"/);
    expect(shellSource).toMatch(/body\.style\.overflow = "hidden"/);
  });

  it("visual-viewport hook drives the mobile shell height + offset", () => {
    const hook = read("hooks/use-visual-viewport-height.ts");
    // Tracks resize/scroll on visualViewport AND window — some iOS
    // versions only fire one or the other when the keyboard opens.
    expect(hook).toMatch(/visualViewport/);
    expect(hook).toMatch(/addEventListener\("resize"/);
    expect(hook).toMatch(/addEventListener\("scroll"/);
    expect(hook).toMatch(/window\.addEventListener\("resize"/);
    // Exposes both height + offsetTop so the shell can ride the
    // visual viewport when iOS scrolls the layout viewport on focus.
    expect(hook).toMatch(/offsetTop/);

    const shell = read("components/mobile/mobile-shell.tsx");
    expect(shell).toMatch(/useVisualViewport/);
    expect(shell).toMatch(/\$\{vp\.height\}px/);
    expect(shell).toMatch(/\$\{vp\.offsetTop\}px/);
  });

  it("root path auto-redirects mobile user agents to /mobile", () => {
    const source = read("middleware.ts");
    expect(source).toMatch(/Mobi\|Android\|iPhone/);
    // ``/mobile`` is the canonical chat-list URL; ``/mobile/sessions``
    // only exists as a backward-compat redirect now.
    expect(source).toMatch(/"\/mobile"/);
    expect(source).not.toMatch(/\/mobile\/sessions/);
    // ``?desktop=1`` opts out so the heatmap stays accessible from
    // the phone when needed.
    expect(source).toMatch(/desktop.*===.*"1"/);
  });

  it("layout exports a mobile viewport config", () => {
    const source = read("app/mobile/layout.tsx");
    expect(source).toMatch(/export const viewport/);
    expect(source).toMatch(/initialScale: 1/);
    expect(source).toMatch(/viewportFit: "cover"/);
  });

  it("/mobile resolves to the most recent chat or a bootstrap fallback", () => {
    const source = read("app/mobile/page.tsx");
    // Full sessions screen is gone — drawer is the only session
    // switcher. ``/mobile`` either redirects into the latest chat or
    // shows a bootstrap fallback when no chat exists yet.
    expect(source).toMatch(/listChatBots/);
    expect(source).toMatch(/listChatSessions/);
    expect(source).toMatch(/redirect\(/);
    expect(source).toMatch(/MobileBootstrapScreen/);
    expect(source).toMatch(/force-dynamic/);
    expect(source).not.toMatch(/MobileSessionsScreen/);
  });

  it("bootstrap screen handles the no-chat / no-bot / offline cases", () => {
    const source = read("components/mobile/mobile-bootstrap-screen.tsx");
    expect(source).toMatch(/apiOnline/);
    expect(source).toMatch(/bots\.length === 0/);
    // Inline session creation uses the Next.js proxy so the phone
    // hits the Mac instead of its own loopback.
    expect(source).toMatch(/"\/api\/chat\/sessions"/);
    expect(source).toMatch(/router\.replace\(/);
  });

  it("/mobile/sessions stays as a backward-compat redirect", () => {
    const source = read("app/mobile/sessions/page.tsx");
    expect(source).toMatch(/redirect\("\/mobile"\)/);
  });

  it("sidebar short-circuits on /mobile to free the viewport", () => {
    const source = read("components/sidebar.tsx");
    expect(source).toMatch(/pathname\.startsWith\("\/mobile"\)/);
    // The early return lives in the public wrapper so React's
    // rules-of-hooks invariant is preserved.
    expect(source).toMatch(/function SidebarImpl/);
  });

  it("drawer session list owns rename / delete / inline-create flows", () => {
    const source = read("components/mobile/sessions-drawer-panel.tsx");
    // Client-side fetches MUST hit the Next.js proxy (``/api/chat/...``)
    // and not the ``abyss-api`` helpers that point at the
    // ``127.0.0.1:3848`` sidecar — on a phone, ``127.0.0.1`` is the
    // phone, not the Mac, so direct calls silently fail.
    expect(source).toMatch(/fetch\(\s*`\/api\/chat\/sessions\?bot=/);
    expect(source).toMatch(/fetch\("\/api\/chat\/sessions"/);
    expect(source).toMatch(/\/rename/);
    expect(source).not.toMatch(/listChatSessions\(/);
    expect(source).not.toMatch(/renameChatSession\(/);
    expect(source).not.toMatch(/deleteChatSession\(/);
    expect(source).not.toMatch(/createChatSession\(/);
    // Custom name takes priority over bot display name (drawer uses
    // ``sess`` as the loop var, sub-dialogs use ``session``).
    expect(source).toMatch(/(?:sess|session)\.custom_name/);
    // Per-row actions: ⋮ button + right-click both open the menu.
    expect(source).toMatch(/onContextMenu/);
    expect(source).toMatch(/MoreVertical/);
  });

  it("api helper exposes renameChatSession and proxy route exists", () => {
    const api = read("lib/abyss-api.ts");
    expect(api).toMatch(/renameChatSession/);
    expect(api).toMatch(/custom_name/);
    const proxy = read(
      "app/api/chat/sessions/[bot]/[id]/rename/route.ts"
    );
    expect(proxy).toMatch(/export async function POST/);
    expect(proxy).toMatch(/renameChatSession\(bot, id/);
  });

  it("chat screen renders header + input bar + workspace + slash sheets", () => {
    const source = read("components/mobile/mobile-chat-screen.tsx");
    // Hamburger opens the sessions slide-drawer rather than
    // navigating away from the chat — the user explicitly asked
    // for the "drawer pushes the chat" pattern.
    expect(source).toMatch(/aria-label="Open sessions"/);
    expect(source).toMatch(/setSessionsOpen\(true\)/);
    expect(source).toMatch(/aria-label="Workspace files"/);
    // Input bar order: slash, attach, textarea, send/voice toggle.
    expect(source).toMatch(/aria-label="Slash commands"/);
    expect(source).toMatch(/aria-label="Attach file"/);
    expect(source).toMatch(/aria-label="Send message"/);
    // Mic button now opens the full conversational voice-mode
    // overlay (mirrors the removed desktop chat-view pattern from
    // c983c9b); the legacy dictation flow is gone on purpose.
    expect(source).toMatch(/Start voice mode/);
    expect(source).toMatch(/handleVoiceOpen/);
    // Workspace + sessions slide in from the side instead of
    // stacking a centred Dialog.
    expect(source).toMatch(/<SlideDrawer/);
    // Workspace sheet reuses the existing WorkspaceTree component.
    expect(source).toMatch(/WorkspaceTree/);
    // Slash command sheet hits the catalog endpoint.
    expect(source).toMatch(/\/api\/chat\/commands/);
    // Streaming hook is reused from desktop so SSE handling stays in
    // one place.
    expect(source).toMatch(/useMultiSessionChatStream/);
  });

  it("chat page resolves session server-side with 404 fallback", () => {
    const source = read("app/mobile/chat/[bot]/[sessionId]/page.tsx");
    expect(source).toMatch(/listChatSessions/);
    expect(source).toMatch(/notFound\(\)/);
    expect(source).toMatch(/MobileChatScreen/);
  });

  it("slash commands proxy route exists", () => {
    const source = read("app/api/chat/commands/route.ts");
    expect(source).toMatch(/export async function GET/);
    expect(source).toMatch(/listSlashCommands/);
  });

  it("stream hook handles command_result events", () => {
    const source = read("components/chat/use-chat-stream.ts");
    expect(source).toMatch(/event\.type === "command_result"/);
  });

  it("ChatEvent type includes command_result with optional file payload", () => {
    const source = read("lib/abyss-api.ts");
    expect(source).toMatch(/type: "command_result"/);
    expect(source).toMatch(/file\?: \{ name: string; path: string; url: string \}/);
  });

  it("LogoSplash holds the screen with inline color and unmounts itself", () => {
    const splash = read("components/mobile/logo-splash.tsx");
    // State-driven fade. CSS keyframes were dropped because the iOS
    // PWA cold start would paint the SSR HTML before the bundled
    // stylesheet (with the @keyframes) loaded, leaving a frame where
    // the chat behind the still-invisible splash flashed through.
    expect(splash).toMatch(/setPhase\("fading-out"\)/);
    expect(splash).toMatch(/transition: `opacity \${FADE_MS}ms/);
    // Inline ``backgroundColor`` so the overlay is solid from the
    // very first paint regardless of CSS load order. Anything that
    // re-introduces the Tailwind background utility is a regression.
    expect(splash).toMatch(/backgroundColor: "#131313"/);
    expect(splash).not.toMatch(/bg-background/);
    // Plain ``<img>`` — ``next/image`` would swap a placeholder in
    // mid-flight.
    expect(splash).toMatch(/<img\b/);
    expect(splash).toMatch(/\/logo-square\.png/);
  });

  it("MobileShell mounts LogoSplash on cold start (no localStorage flag)", () => {
    const shell = read("components/mobile/mobile-shell.tsx");
    expect(shell).toMatch(/from "@\/components\/mobile\/logo-splash"/);
    // Cold-start surface: initial state is "visible" and there is no
    // localStorage check — every mount of the shell shows the splash.
    expect(shell).toMatch(/useState\(true\)/);
    expect(shell).not.toMatch(/localStorage/);
    expect(shell).toMatch(/splashVisible && <LogoSplash/);
  });

  it("root layout paints the document background dark before CSS loads", () => {
    // The actual root cause of the "한 번 깜빡임" report was the
    // standard iOS PWA white frame between the system splash and
    // the first React paint, not anything inside LogoSplash itself.
    // The fix lives in the root ``<head>`` as an inline ``<style>``
    // so the document is dark from the very first byte. This guard
    // makes sure nobody removes it later thinking it is dead code.
    const layout = read("app/layout.tsx");
    expect(layout).toMatch(/<style>\{?"html,body\{background-color:#131313;\}"\}?<\/style>/);
  });

  it("sessions drawer shows a streaming indicator on rows mid-reply", () => {
    const panel = read("components/mobile/sessions-drawer-panel.tsx");
    // Subscribes to the module-level streaming store so the
    // indicator lights up even on rows the user is not viewing.
    expect(panel).toMatch(/useMultiSessionChatStream/);
    expect(panel).toMatch(/getSessionStream\(stream\.streams, sess\.id\)/);
    // Renders a pulsing emerald dot + swaps the preview line for an
    // explicit Korean "진행중" message.
    expect(panel).toMatch(/stream-pulse/);
    expect(panel).toMatch(/aria-label="진행중"/);
    expect(panel).toMatch(/응답 생성 중/);
    // Pulse keyframes live in globals.css next to the existing
    // stream-dot ones so the indicator works without inline keyframes.
    const css = read("app/globals.css");
    expect(css).toMatch(/@keyframes stream-pulse/);
  });

  it("ChatEvent + stream hook handle the reset_partial signal", () => {
    // chat_core emits a ``reset_partial`` SSE event between retries when
    // the upstream Claude API returned a retryable 5xx. The hook must
    // wipe its in-progress accumulator so the retry's clean reply does
    // not concatenate onto the leaked JSON error chunk.
    const api = read("lib/abyss-api.ts");
    expect(api).toMatch(/type: "reset_partial"/);
    const hook = read("components/chat/use-chat-stream.ts");
    expect(hook).toMatch(/event\.type === "reset_partial"/);
    expect(hook).toMatch(/accumulated = ""/);
  });

  it("chat screen renders assistant replies through ReactMarkdown", () => {
    const source = read("components/mobile/mobile-chat-screen.tsx");
    // Markdown rendering shares the desktop `prose prose-sm`
    // typography setup so headings / lists / links / code blocks
    // render the same on both surfaces.
    expect(source).toMatch(/import ReactMarkdown from "react-markdown"/);
    expect(source).toMatch(/function MarkdownBody/);
    expect(source).toMatch(/prose prose-sm/);
    // User bubbles stay as plain pre-wrap text — only the assistant
    // side parses markdown.
    expect(source).toMatch(/isUser \? \(\s*<div className="whitespace-pre-wrap">/);
  });

  it("chat screen hides the textarea scrollbar across browser engines", () => {
    const source = read("components/mobile/mobile-chat-screen.tsx");
    expect(source).toMatch(/\[&::-webkit-scrollbar\]:hidden/);
    expect(source).toMatch(/scrollbarWidth: "none"/);
    expect(source).toMatch(/msOverflowStyle: "none"/);
  });

  it("chat screen jumps to the latest message on first paint", () => {
    const source = read("components/mobile/mobile-chat-screen.tsx");
    // Long transcripts should not smooth-scroll from the top down on
    // entry. First paint uses ``instant`` so the user lands on the
    // newest reply immediately; subsequent updates stay smooth.
    expect(source).toMatch(/firstScrollRef/);
    expect(source).toMatch(/behavior: "instant"/);
    expect(source).toMatch(/useLayoutEffect/);
  });

  it("stream hook forwards command_result file payload to the caller", () => {
    const source = read("components/chat/use-chat-stream.ts");
    // The hook must thread ``event.file`` through to the caller —
    // dropping it makes ``/send <filename>`` render as a blank
    // assistant bubble (codex P1 review on PR #50).
    expect(source).toMatch(/event\.file \?\? null/);
    // SendResult is the new return shape; both surfaces consume it.
    expect(source).toMatch(/SendResult/);
    expect(source).toMatch(/commandFile/);
  });

  it("optimistic attachment URLs use the stored real_name, not the original filename", () => {
    const source = read("components/mobile/mobile-chat-screen.tsx");
    // ``uploaded.path`` is ``uploads/<uuid>__<name>``; the file
    // endpoint expects the ``<uuid>__<name>`` portion. Previous
    // revisions used ``display_name`` and produced 404 links until
    // the chat reloaded from history (codex P2 review on PR #50).
    expect(source).toMatch(/startsWith\("uploads\/"\)/);
    expect(source).toMatch(/realName/);
    expect(source).not.toMatch(/url: attachmentUrl\([^,]+,\s*[^,]+,\s*p\.uploaded!\.display_name/);
  });

  it("mobile chat renders a download chip for /send command_file payloads", () => {
    const source = read("components/mobile/mobile-chat-screen.tsx");
    expect(source).toMatch(/message\.commandFile/);
    expect(source).toMatch(/href=\{message\.commandFile\.url\}/);
  });

  // The desktop chat-message component was deleted along with the
  // ``/chat`` route — mobile is the sole chat surface now, and the
  // command-file chip lives in ``mobile-chat-screen.tsx`` (asserted
  // earlier in this suite).

  it("service worker handles push and notificationclick", () => {
    const swPath = path.resolve(
      __dirname,
      "..",
      "..",
      "..",
      "..",
      "public",
      "sw.js"
    );
    const source = readFileSync(swPath, "utf8");
    // SW shows notifications + routes clicks to the chat that fired.
    expect(source).toMatch(/addEventListener\("push"/);
    expect(source).toMatch(/addEventListener\("notificationclick"/);
    expect(source).toMatch(/showNotification/);
    expect(source).toMatch(/\/mobile\/chat\/\$\{bot\}\/\$\{sessionId\}/);
  });

  it("manifest declares PWA fields needed for iOS + Android install", () => {
    const source = read("app/manifest.ts");
    expect(source).toMatch(/start_url: "\/mobile"/);
    expect(source).toMatch(/display: "standalone"/);
    expect(source).toMatch(/android-chrome-192x192\.png/);
    expect(source).toMatch(/android-chrome-512x512\.png/);
    expect(source).toMatch(/purpose: "maskable"/);
  });

  it("root layout points at the manifest + Apple PWA meta", () => {
    const source = read("app/layout.tsx");
    expect(source).toMatch(/manifest: "\/manifest\.webmanifest"/);
    expect(source).toMatch(/appleWebApp:/);
    expect(source).toMatch(/capable: true/);
    // Pretendard wiring stays intact.
    expect(source).toMatch(/--font-pretendard/);
  });

  it("use-web-push hook covers permission + subscribe + visibility", () => {
    const source = read("hooks/use-web-push.ts");
    expect(source).toMatch(/Notification\.requestPermission/);
    expect(source).toMatch(/pushManager\.subscribe/);
    expect(source).toMatch(/\/api\/push\/vapid-key/);
    expect(source).toMatch(/\/api\/push\/subscribe/);
    expect(source).toMatch(/\/api\/push\/visibility/);
    // Notification clicks route the user back to the chat that fired.
    expect(source).toMatch(/\/mobile\/chat\/\$\{nav\.bot\}\/\$\{nav\.sessionId\}/);
    // Visibility heartbeat fires while the tab is focused.
    expect(source).toMatch(/setInterval/);
  });

  it("push toggle lives in its own module and is mounted in the drawer footer", () => {
    const toggle = read("components/mobile/push-toggle.tsx");
    expect(toggle).toMatch(/export function PushToggle/);
    // Reads from the shared provider — calling ``useWebPush``
    // directly here would mount a second instance and re-register
    // notification-click + visibility listeners.
    expect(toggle).toMatch(/useWebPushContext/);
    expect(toggle).not.toMatch(/= useWebPush\(/);
    expect(toggle).toMatch(/Add to Home Screen/);

    const drawer = read("components/mobile/sessions-drawer-panel.tsx");
    expect(drawer).toMatch(/import \{ PushToggle \}/);
    expect(drawer).toMatch(/<PushToggle \/>/);
  });

  it("root layout mounts WebPushProvider once for every page", () => {
    const source = read("app/layout.tsx");
    // codex P1+P2 review on PR #51: notification-click routing and
    // visibility tracking must run on every page, not just the
    // sessions list. The provider hoists ``useWebPush`` to the root
    // so any page in the React tree benefits.
    expect(source).toMatch(/WebPushProvider/);
    expect(source).toMatch(/<WebPushProvider>/);
  });

  it("WebPushProvider exposes a context guard", () => {
    const source = read("components/web-push-provider.tsx");
    expect(source).toMatch(/createContext/);
    expect(source).toMatch(/useWebPushContext/);
    expect(source).toMatch(/must be called inside <WebPushProvider>/);
  });

  it("api proxy routes forward to the chat server push endpoints", () => {
    const subscribe = read("app/api/push/subscribe/route.ts");
    expect(subscribe).toMatch(/\/chat\/push\/subscribe/);
    expect(subscribe).toMatch(/export async function POST/);
    expect(subscribe).toMatch(/export async function DELETE/);

    const vapid = read("app/api/push/vapid-key/route.ts");
    expect(vapid).toMatch(/\/chat\/push\/vapid-key/);

    const visibility = read("app/api/push/visibility/route.ts");
    expect(visibility).toMatch(/\/chat\/push\/visibility/);
    expect(visibility).toMatch(/keepalive: true/);
  });

  // ``handlers.py`` was the Telegram adapter — it was deleted in
  // v2026.05.14 when the PWA + dashboard chat became the only
  // surface. The original assertion (file-handle closure on
  // ``reply_document``) had no remaining production code to guard.

it("workspace and sessions slide in from the side instead of a centred modal", () => {
    const source = read("components/mobile/mobile-chat-screen.tsx");
    // Workspace + sessions both go through the shared SlideDrawer
    // primitive. The Dialog-based workspace (with its showCloseButton
    // and sr-only DialogTitle dance to avoid a duplicated header)
    // is gone — the slide drawer lets WorkspaceTree own the chrome
    // naturally, and the user gets the "push the chat aside" feel
    // they asked for.
    expect(source).toMatch(/side="right"/);
    expect(source).toMatch(/side="left"/);
    // The user is no longer routed off to ``/mobile`` for sessions;
    // hamburger now just opens the drawer.
    expect(source).not.toMatch(/href="\/mobile"/);
  });

  it("SlideDrawer is a generic left/right side drawer with backdrop", () => {
    const source = read("components/mobile/slide-drawer.tsx");
    expect(source).toMatch(/side: "left" \| "right"/);
    expect(source).toMatch(/Escape/);
    expect(source).toMatch(/translate-x-0/);
    expect(source).toMatch(/-translate-x-full/);
  });

  it("chat screen wires conversational voice mode and swipe navigation", () => {
    const source = read("components/mobile/mobile-chat-screen.tsx");
    // Mic button used to feed a dictation pipeline (transcript →
    // textarea). It now opens a full-screen Orb voice mode that
    // mirrors the desktop chat-view pattern removed in c983c9b:
    // speak → auto-submit with ``voice_mode: true`` → reply TTS'd
    // → recording auto-restarts.
    expect(source).toMatch(/useVoiceMode/);
    expect(source).toMatch(/VoiceScreen/);
    expect(source).toMatch(/voiceMode/);
    // Auto-submit goes through submitTranscript with voiceFlag=true.
    expect(source).toMatch(/submitTranscript/);
    expect(source).toMatch(/voiceFlag: true/);
    // Auto-restart after TTS: prev=speaking → cur=idle.
    expect(source).toMatch(/prev === "speaking"/);
    // Horizontal swipes on the message area page between sibling
    // sessions of the same bot.
    expect(source).toMatch(/onMessagesTouchStart/);
    expect(source).toMatch(/goToSibling/);
  });

  it("voice-screen renders the Orb with theme-aware colors and a close button", () => {
    const source = read("components/chat/voice-screen.tsx");
    expect(source).toMatch(/import \{ Orb/);
    expect(source).toMatch(/useTheme/);
    expect(source).toMatch(/onClose/);
    // State → AgentState mapping must be present so the Orb actually
    // animates between listening / thinking / talking.
    expect(source).toMatch(/toAgentState/);
    expect(source).toMatch(/partialTranscript/);
  });
});
