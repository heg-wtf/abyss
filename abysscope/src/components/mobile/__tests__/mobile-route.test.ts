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
  it("layout uses fixed full-screen wrapper with safe-area padding", () => {
    const source = read("app/mobile/layout.tsx");
    expect(source).toMatch(/fixed inset-0/);
    expect(source).toMatch(/safe-area-inset-top/);
    expect(source).toMatch(/safe-area-inset-bottom/);
  });

  it("layout exports a mobile viewport config", () => {
    const source = read("app/mobile/layout.tsx");
    expect(source).toMatch(/export const viewport/);
    expect(source).toMatch(/initialScale: 1/);
    expect(source).toMatch(/viewportFit: "cover"/);
  });

  it("index page redirects to /mobile/sessions", () => {
    const source = read("app/mobile/page.tsx");
    expect(source).toMatch(/redirect\("\/mobile\/sessions"\)/);
  });

  it("sessions page fetches bots server-side and renders the screen", () => {
    const source = read("app/mobile/sessions/page.tsx");
    expect(source).toMatch(/listChatBots/);
    expect(source).toMatch(/MobileSessionsScreen/);
    expect(source).toMatch(/force-dynamic/);
  });

  it("sidebar short-circuits on /mobile to free the viewport", () => {
    const source = read("components/sidebar.tsx");
    expect(source).toMatch(/pathname\.startsWith\("\/mobile"\)/);
    // The early return lives in the public wrapper so React's
    // rules-of-hooks invariant is preserved.
    expect(source).toMatch(/function SidebarImpl/);
  });

  it("mobile sessions screen wires bot picker, rename, and delete flows", () => {
    const source = read("components/mobile/mobile-sessions-screen.tsx");
    // Bot picker uses base-ui Menu (matches the desktop chat-session-list).
    expect(source).toMatch(/Menu\.Root/);
    expect(source).toMatch(/createChatSession/);
    // Custom name renames go through the new API helper.
    expect(source).toMatch(/renameChatSession/);
    expect(source).toMatch(/deleteChatSession/);
    // Long-press contract: touchstart + touchend cancel.
    expect(source).toMatch(/useLongPress/);
    expect(source).toMatch(/onTouchStart/);
    expect(source).toMatch(/onTouchEnd/);
    // Custom name takes priority over bot display name.
    expect(source).toMatch(/session\.custom_name/);
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
    // Header has back link to sessions list and workspace toggle.
    expect(source).toMatch(/href="\/mobile\/sessions"/);
    expect(source).toMatch(/aria-label="Workspace files"/);
    // Input bar order: slash, attach, textarea, send/voice toggle.
    expect(source).toMatch(/aria-label="Slash commands"/);
    expect(source).toMatch(/aria-label="Attach file"/);
    expect(source).toMatch(/aria-label="Send message"/);
    expect(source).toMatch(/aria-label="Voice/);
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

  it("workspace sheet defers its chrome to WorkspaceTree's own header", () => {
    const source = read("components/mobile/mobile-chat-screen.tsx");
    // WorkspaceTree already renders a header with Workspace title +
    // Finder + Refresh + Close buttons. Letting the Dialog render its
    // own header / close button would surface two titles and two X
    // buttons (the bug the user reported). We keep the title in
    // sr-only form for a11y and disable the Dialog's built-in close.
    expect(source).toMatch(/showCloseButton=\{false\}/);
    expect(source).toMatch(/DialogTitle className="sr-only">Workspace/);
  });
});
