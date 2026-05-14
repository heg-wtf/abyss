/**
 * Source-level regression guards.
 *
 * Several UI fixes have been silently dropped during squash merges (the
 * `bot_display_name` rendering and the sidebar collapse toggle were both
 * lost twice). These checks read the relevant source files and assert that
 * the load-bearing snippets are still in place. They run in the existing
 * Vitest (node env) suite without any extra DOM dependency.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

function read(relPath: string): string {
  return readFileSync(path.join(ROOT, relPath), "utf8");
}

describe("UI regression guards", () => {
  // The desktop ``/chat`` surface (chat-view, chat-session-list,
  // chat-message, bot-selector, prompt-input, voice-screen) was
  // removed once the mobile shell became the canonical chat surface.
  // The display-name + per-session-stream guards now live in the
  // mobile regression suite (`mobile/__tests__/mobile-route.test.ts`).

  it("Sidebar exposes a collapse toggle persisted to localStorage", () => {
    const source = read("sidebar.tsx");
    expect(source).toMatch(/abysscope\.sidebar\.collapsed/);
    // Both expand and collapse buttons must be present.
    expect(source).toMatch(/aria-label="Collapse sidebar"/);
    expect(source).toMatch(/aria-label="Expand sidebar"/);
  });

  it("Sidebar no longer links to the deleted /chat route", () => {
    const source = read("sidebar.tsx");
    // The Chat menu item + its CollapsedLink twin were removed when
    // the desktop chat surface went away. Catching either link
    // resurfacing here keeps a careless squash from re-adding a
    // dead route.
    expect(source).not.toMatch(/href="\/chat"/);
    expect(source).not.toMatch(/label="Chat"/);
  });
});
