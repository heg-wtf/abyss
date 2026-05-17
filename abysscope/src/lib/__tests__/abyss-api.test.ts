import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  attachmentUrl,
  formatBotLabel,
  markRoutineRead,
  markSessionRead,
  parseChatEvents,
  setUnreadBadge,
  uploadAttachment,
  UpstreamError,
  type ChatEvent,
} from "@/lib/abyss-api";

function streamFromChunks(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

async function collect(
  stream: ReadableStream<Uint8Array>
): Promise<ChatEvent[]> {
  const events: ChatEvent[] = [];
  for await (const event of parseChatEvents(stream)) {
    events.push(event);
  }
  return events;
}

describe("parseChatEvents", () => {
  it("parses chunk and done events", async () => {
    const stream = streamFromChunks([
      'data: {"type":"chunk","text":"hi "}\n\n',
      'data: {"type":"chunk","text":"there"}\n\n',
      'data: {"type":"done","text":"hi there"}\n\n',
    ]);
    const events = await collect(stream);
    expect(events.map((event) => event.type)).toEqual(["chunk", "chunk", "done"]);
  });

  it("handles events split across chunk boundaries", async () => {
    const stream = streamFromChunks([
      'data: {"type":"chu',
      'nk","text":"split"}\n\nda',
      'ta: {"type":"done","text":"split"}\n\n',
    ]);
    const events = await collect(stream);
    expect(events).toEqual([
      { type: "chunk", text: "split" },
      { type: "done", text: "split" },
    ]);
  });

  it("ignores malformed JSON without throwing", async () => {
    const stream = streamFromChunks([
      "data: {garbage}\n\n",
      'data: {"type":"chunk","text":"ok"}\n\n',
    ]);
    const events = await collect(stream);
    expect(events).toEqual([{ type: "chunk", text: "ok" }]);
  });

  it("surfaces error events", async () => {
    const stream = streamFromChunks([
      'data: {"type":"error","message":"boom"}\n\n',
    ]);
    const events = await collect(stream);
    expect(events).toEqual([{ type: "error", message: "boom" }]);
  });
});

describe("uploadAttachment", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn() as typeof globalThis.fetch;
  });

  it("posts FormData with bot/session/file and returns the path payload", async () => {
    const mockResponse = {
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: () =>
        Promise.resolve({
          path: "uploads/abc12345__photo.png",
          display_name: "photo.png",
          mime: "image/png",
          size: 42,
        }),
    };
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      mockResponse as unknown as Response
    );

    const file = new File(["\x89PNG"], "photo.png", { type: "image/png" });
    const result = await uploadAttachment("alpha", "chat_web_abc123", file);

    expect(result.path).toBe("uploads/abc12345__photo.png");
    expect(result.size).toBe(42);
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/chat/upload");
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    const form = init.body as FormData;
    expect(form.get("bot")).toBe("alpha");
    expect(form.get("session_id")).toBe("chat_web_abc123");
    expect(form.get("file")).toBeInstanceOf(File);
  });

  it("throws UpstreamError on 4xx so callers can surface the reason", async () => {
    const mockResponse = {
      ok: false,
      status: 400,
      headers: new Headers({ "Content-Type": "application/json" }),
      text: () => Promise.resolve('{"error":"invalid_mime"}'),
    };
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      mockResponse as unknown as Response
    );

    const file = new File(["text"], "note.txt", { type: "text/plain" });
    await expect(
      uploadAttachment("alpha", "chat_web_abc123", file)
    ).rejects.toBeInstanceOf(UpstreamError);
  });
});

describe("attachmentUrl", () => {
  it("URL-encodes path segments", () => {
    expect(attachmentUrl("alpha bot", "chat_web_abc", "a/b.png")).toBe(
      "/api/chat/sessions/alpha%20bot/chat_web_abc/file/a%2Fb.png"
    );
  });
});

describe("markSessionRead / markRoutineRead", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn() as typeof globalThis.fetch;
  });

  it("posts to the per-session read endpoint", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: () => Promise.resolve({ last_read_at: "2026-05-18T05:00:00Z" }),
    });

    await markSessionRead("alpha bot", "chat_web_abc");

    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(String(call[0])).toMatch(
      /\/chat\/sessions\/alpha%20bot\/chat_web_abc\/read$/,
    );
    expect(call[1]?.method).toBe("POST");
  });

  it("posts to the per-routine read endpoint with kind segment", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: () => Promise.resolve({ last_read_at: "2026-05-18T05:00:00Z" }),
    });

    await markRoutineRead("alpha", "cron", "daily brief");

    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(String(call[0])).toMatch(
      /\/chat\/routines\/alpha\/cron\/daily%20brief\/read$/,
    );
    expect(call[1]?.method).toBe("POST");
  });
});

describe("formatBotLabel", () => {
  it("appends alias in parens when present", () => {
    expect(formatBotLabel({ display_name: "앤", alias: "집사" })).toBe(
      "앤 (집사)",
    );
  });

  it("returns the bare display name when alias is null", () => {
    expect(formatBotLabel({ display_name: "앤", alias: null })).toBe("앤");
  });

  it("treats whitespace-only alias as absent", () => {
    expect(formatBotLabel({ display_name: "앤", alias: "   " })).toBe("앤");
  });

  it("trims both fields", () => {
    expect(
      formatBotLabel({ display_name: "  앤  ", alias: "  집사  " }),
    ).toBe("앤 (집사)");
  });
});

describe("setUnreadBadge", () => {
  type BadgeNav = Navigator & {
    setAppBadge?: ReturnType<typeof vi.fn>;
    clearAppBadge?: ReturnType<typeof vi.fn>;
  };
  let originalSet: BadgeNav["setAppBadge"];
  let originalClear: BadgeNav["clearAppBadge"];

  beforeEach(() => {
    const nav = navigator as BadgeNav;
    originalSet = nav.setAppBadge;
    originalClear = nav.clearAppBadge;
    nav.setAppBadge = vi.fn().mockResolvedValue(undefined);
    nav.clearAppBadge = vi.fn().mockResolvedValue(undefined);
  });

  afterEach(() => {
    const nav = navigator as BadgeNav;
    nav.setAppBadge = originalSet;
    nav.clearAppBadge = originalClear;
  });

  it("calls setAppBadge with the count when positive", () => {
    setUnreadBadge(3);
    const nav = navigator as BadgeNav;
    expect(nav.setAppBadge).toHaveBeenCalledWith(3);
    expect(nav.clearAppBadge).not.toHaveBeenCalled();
  });

  it("clears the badge when count is zero", () => {
    setUnreadBadge(0);
    const nav = navigator as BadgeNav;
    expect(nav.clearAppBadge).toHaveBeenCalled();
    expect(nav.setAppBadge).not.toHaveBeenCalled();
  });
});
