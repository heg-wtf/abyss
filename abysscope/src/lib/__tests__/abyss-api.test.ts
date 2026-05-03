import { describe, expect, it } from "vitest";
import { parseChatEvents, type ChatEvent } from "@/lib/abyss-api";

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
