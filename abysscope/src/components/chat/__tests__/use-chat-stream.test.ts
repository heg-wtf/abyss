/**
 * Pure-helper + source-level guards for the multi-session chat stream hook.
 *
 * The hook itself manipulates React state + AbortController, which requires a
 * DOM env to render. abysscope's vitest config is node-only and we do not want
 * to pull in jsdom + @testing-library just for a single hook. Instead we cover:
 *
 * 1. `getSessionStream` pure helper — exhaustive cases.
 * 2. Source-level regression guards — verify the hook keeps per-session
 *    isolation (AbortController Map, sessionId-keyed send/cancel). Squash
 *    merges have silently regressed similar UI fixes before, so the source
 *    guards mirror the existing ui-regression.test.ts pattern.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  getSessionStream,
  type SessionStream,
} from "../use-chat-stream";

const HOOK_SOURCE = readFileSync(
  path.resolve(__dirname, "..", "use-chat-stream.ts"),
  "utf8"
);

describe("getSessionStream", () => {
  const sample: SessionStream = {
    text: "hello",
    streaming: true,
    error: null,
  };

  it("returns empty stream when sessionId is null", () => {
    const result = getSessionStream(new Map(), null);
    expect(result.text).toBe("");
    expect(result.streaming).toBe(false);
    expect(result.error).toBeNull();
  });

  it("returns empty stream when sessionId is undefined", () => {
    const result = getSessionStream(new Map(), undefined);
    expect(result.streaming).toBe(false);
  });

  it("returns empty stream when sessionId is missing from the map", () => {
    const map = new Map<string, SessionStream>([["other", sample]]);
    const result = getSessionStream(map, "missing");
    expect(result.text).toBe("");
    expect(result.streaming).toBe(false);
  });

  it("returns the stream when present", () => {
    const map = new Map<string, SessionStream>([["abc", sample]]);
    const result = getSessionStream(map, "abc");
    expect(result).toEqual(sample);
  });

  it("treats each sessionId independently", () => {
    const a: SessionStream = { text: "A", streaming: true, error: null };
    const b: SessionStream = { text: "B", streaming: false, error: "boom" };
    const map = new Map<string, SessionStream>([
      ["a", a],
      ["b", b],
    ]);
    expect(getSessionStream(map, "a")).toEqual(a);
    expect(getSessionStream(map, "b")).toEqual(b);
  });
});

describe("useMultiSessionChatStream source guards", () => {
  it("keeps streaming state at module scope, not inside a hook", () => {
    // The hook subscribes to a module-level store so streaming survives
    // component unmount / route navigation. A legacy ``useState`` over the
    // map would silently lose every in-flight stream on the first nav.
    expect(HOOK_SOURCE).toMatch(/const streamMap = new Map<string, SessionStream>\(\)/);
    expect(HOOK_SOURCE).toMatch(/const controllerMap = new Map<string, AbortController>\(\)/);
    expect(HOOK_SOURCE).not.toMatch(/useState<Map<string,\s*SessionStream>>/);
  });

  it("keys AbortControllers by sessionId, not a single ref", () => {
    // One controller per session — never re-introduce a global abortRef.
    expect(HOOK_SOURCE).not.toMatch(
      /abortRef\s*=\s*useRef<AbortController\s*\|\s*null>/
    );
  });

  it("abort on send only touches the same session's controller", () => {
    // Regression guard: if someone ever rewrites this to abort *all*
    // in-flight streams on send (the original bug), the chat input would
    // disable globally again. Pin the per-session lookup.
    expect(HOOK_SOURCE).toMatch(
      /controllerMap\.get\(sessionId\)\?\.abort\(\)/
    );
  });

  it("cancel signature takes a sessionId argument", () => {
    expect(HOOK_SOURCE).toMatch(/cancel:\s*\(sessionId:\s*string\)\s*=>\s*void/);
    expect(HOOK_SOURCE).toMatch(/cancelAll:\s*\(\)\s*=>\s*void/);
  });

  it("exposes streams as a Map keyed by sessionId", () => {
    expect(HOOK_SOURCE).toMatch(/streams:\s*Map<string,\s*SessionStream>/);
  });

  it("does NOT abort streams on hook unmount", () => {
    // The whole point of moving state to module scope is that an in-flight
    // reply must continue while the user navigates away. A ``useEffect``
    // cleanup that walks the controller map and calls ``.abort()`` would
    // undo that. Stay vigilant against accidental re-introduction.
    expect(HOOK_SOURCE).not.toMatch(/for \(const controller of controllers\.values/);
    expect(HOOK_SOURCE).not.toMatch(/return\s*\(\)\s*=>\s*\{[^}]*abort\(\)/);
  });

  it("uses useSyncExternalStore to subscribe React components", () => {
    // The React 18 way to bind a mutable external store to a component.
    // Replacing it with manual state would re-introduce the lost-on-unmount
    // bug because there'd be no shared source of truth across mounts.
    expect(HOOK_SOURCE).toMatch(/useSyncExternalStore\(subscribe,/);
  });
});
