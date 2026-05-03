import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  attachmentUrl,
  parseChatEvents,
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
