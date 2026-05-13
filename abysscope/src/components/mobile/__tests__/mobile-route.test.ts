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

  it("placeholder screen calls out Phase 2 status and links back to desktop", () => {
    const source = read("components/mobile/mobile-sessions-screen.tsx");
    expect(source).toMatch(/Phase 2 skeleton/);
    expect(source).toMatch(/href="\/chat"/);
  });
});
