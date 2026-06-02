// @vitest-environment happy-dom
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/use-multi-session-chat-stream", () => ({
  useMultiSessionChatStream: () => new Set<string>(),
}));

vi.mock("@/lib/abyss-api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/abyss-api")>(
    "@/lib/abyss-api",
  );
  return {
    ...actual,
    setUnreadBadge: vi.fn(),
  };
});

import { SessionsDrawerPanel } from "../sessions-drawer-panel";

const fetchMock = vi.fn(async (url: string) => {
  if (url.startsWith("/api/chat/bots")) {
    return new Response(JSON.stringify({ bots: [] }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }
  if (url.startsWith("/api/chat/sessions")) {
    return new Response(JSON.stringify({ sessions: [] }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }
  if (url.startsWith("/api/chat/routines")) {
    return new Response(JSON.stringify({ routines: [] }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }
  return new Response("not found", { status: 404 });
});

describe("SessionsDrawerPanel — initialTab", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockClear();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("defaults to the Chats tab when initialTab is omitted", async () => {
    render(
      <SessionsDrawerPanel
        activeBot=""
        activeSessionId=""
        onSelect={() => {}}
        onCreate={() => {}}
      />,
    );
    await waitFor(() => {
      const chatsTab = screen.getByRole("button", { name: /^Chats$/i });
      expect(chatsTab.getAttribute("aria-pressed")).toBe("true");
    });
    const routinesTab = screen.getByRole("button", { name: /^Routines$/i });
    expect(routinesTab.getAttribute("aria-pressed")).toBe("false");
  });

  it("opens on the Routines tab when initialTab='routines'", async () => {
    render(
      <SessionsDrawerPanel
        activeBot=""
        activeSessionId=""
        onSelect={() => {}}
        onCreate={() => {}}
        initialTab="routines"
      />,
    );
    await waitFor(() => {
      const routinesTab = screen.getByRole("button", { name: /^Routines$/i });
      expect(routinesTab.getAttribute("aria-pressed")).toBe("true");
    });
    const chatsTab = screen.getByRole("button", { name: /^Chats$/i });
    expect(chatsTab.getAttribute("aria-pressed")).toBe("false");
    // The Routines tab being active should trigger the routines fetch.
    await waitFor(() => {
      const routineCalls = fetchMock.mock.calls.filter((call) =>
        String(call[0]).startsWith("/api/chat/routines"),
      );
      expect(routineCalls.length).toBeGreaterThan(0);
    });
  });
});
