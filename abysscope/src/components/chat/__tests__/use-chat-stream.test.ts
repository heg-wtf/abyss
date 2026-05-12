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
  it("keys AbortControllers by sessionId, not a single ref", () => {
    // The whole point of the refactor: one controller per session.
    expect(HOOK_SOURCE).toMatch(
      /controllersRef\s*=\s*useRef<Map<string,\s*AbortController>>/
    );
    // The legacy single-ref pattern must not return.
    expect(HOOK_SOURCE).not.toMatch(
      /abortRef\s*=\s*useRef<AbortController\s*\|\s*null>/
    );
  });

  it("abort on send only touches the same session's controller", () => {
    // Regression guard: if someone ever rewrites this to abort *all*
    // in-flight streams on send (the original bug), the chat input would
    // disable globally again. Pin the per-session lookup.
    expect(HOOK_SOURCE).toMatch(
      /controllersRef\.current\.get\(sessionId\)\?\.abort\(\)/
    );
  });

  it("cancel signature takes a sessionId argument", () => {
    expect(HOOK_SOURCE).toMatch(/cancel:\s*\(sessionId:\s*string\)\s*=>\s*void/);
    expect(HOOK_SOURCE).toMatch(/cancelAll:\s*\(\)\s*=>\s*void/);
  });

  it("exposes streams as a Map keyed by sessionId", () => {
    expect(HOOK_SOURCE).toMatch(/streams:\s*Map<string,\s*SessionStream>/);
  });

  it("aborts every controller on unmount", () => {
    // useEffect cleanup must walk the Map. A plain `abortRef.abort()` would
    // leave background streams running after the component unmounts.
    expect(HOOK_SOURCE).toMatch(/for \(const controller of controllers\.values/);
  });
});
