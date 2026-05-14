/**
 * Source-level guards for the workspace-tree side panel.
 *
 * The vitest suite runs in a node env without jsdom, so we cover behavioural
 * guarantees by reading the source and asserting the load-bearing snippets
 * are present. This mirrors src/components/__tests__/ui-regression.test.ts.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

function read(relPath: string): string {
  return readFileSync(path.join(ROOT, relPath), "utf8");
}

describe("WorkspaceTree component guards", () => {
  const source = read("workspace-tree.tsx");

  it("refetches when bot or sessionId changes", () => {
    expect(source).toMatch(/loadRoot/);
    expect(source).toMatch(/\[bot, sessionId\]/);
  });

  it("lazy-loads children on directory expand", () => {
    expect(source).toMatch(/fetchTree\(bot, sessionId, key\)/);
    expect(source).toMatch(/childrenByPath/);
  });

  it("renders close button calling onClose", () => {
    expect(source).toMatch(/onClick=\{onClose\}/);
  });

  it("opens workspace root in Finder via existing endpoint", () => {
    expect(source).toMatch(/"\/api\/open-finder"/);
  });

  it("hits the workspace API with bot, session, and path", () => {
    expect(source).toMatch(/\/api\/chat\/workspace\?/);
    expect(source).toMatch(/params\.set\("path", relativePath\)/);
  });
});

describe("WorkspaceTree mobile integration", () => {
  // The desktop ``/chat`` page was deleted along with its
  // ``chat-view.tsx`` consumer. WorkspaceTree now only mounts from
  // ``mobile-chat-screen.tsx`` inside the right slide-drawer.
  const source = readFileSync(
    path.resolve(__dirname, "..", "..", "mobile", "mobile-chat-screen.tsx"),
    "utf8",
  );

  it("imports WorkspaceTree", () => {
    expect(source).toMatch(/from "@\/components\/chat\/workspace-tree"/);
    expect(source).toMatch(/WorkspaceTree/);
  });

  it("renders inside the SlideDrawer", () => {
    expect(source).toMatch(/SlideDrawer/);
    expect(source).toMatch(/<WorkspaceTree/);
  });
});
