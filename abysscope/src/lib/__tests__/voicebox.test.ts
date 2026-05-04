import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  checkVoiceboxHealth,
  listVoiceProfiles,
  synthesize,
  transcribe,
  VoiceboxError,
} from "@/lib/voicebox";

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("checkVoiceboxHealth", () => {
  it("returns true when proxy responds with ok=true", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    expect(await checkVoiceboxHealth()).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/voice/status",
      expect.objectContaining({ method: "GET" })
    );
  });

  it("returns false on 503", async () => {
    fetchMock.mockResolvedValueOnce(new Response("", { status: 503 }));
    expect(await checkVoiceboxHealth()).toBe(false);
  });

  it("returns false when fetch throws", async () => {
    fetchMock.mockRejectedValueOnce(new Error("network down"));
    expect(await checkVoiceboxHealth()).toBe(false);
  });

  it("returns false when ok flag missing", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({}), { status: 200 })
    );
    expect(await checkVoiceboxHealth()).toBe(false);
  });
});

describe("listVoiceProfiles", () => {
  it("returns the profile array verbatim", async () => {
    const fakeProfiles = [
      { id: "p1", name: "Default", language: "ko" },
      { id: "p2", name: "Narrator", language: "en" },
    ];
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(fakeProfiles), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    const result = await listVoiceProfiles();
    expect(result).toEqual(fakeProfiles);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/voice/profiles",
      expect.objectContaining({ method: "GET" })
    );
  });

  it("returns empty array when payload is not an array", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({}), { status: 200 })
    );
    expect(await listVoiceProfiles()).toEqual([]);
  });

  it("throws VoiceboxError on non-2xx", async () => {
    fetchMock.mockResolvedValueOnce(new Response("oops", { status: 503 }));
    await expect(listVoiceProfiles()).rejects.toBeInstanceOf(VoiceboxError);
  });
});

describe("transcribe", () => {
  it("posts FormData with default ko + large and returns text", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ text: "안녕", duration: 1.2 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    const blob = new Blob(["fake-audio"], { type: "audio/webm" });
    const result = await transcribe(blob);

    expect(result.text).toBe("안녕");
    expect(result.duration).toBe(1.2);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/voice/transcribe");
    expect(init.method).toBe("POST");
    const body = init.body as FormData;
    expect(body.get("language")).toBe("ko");
    expect(body.get("model")).toBe("large");
    // Voicebox expects the binary part to be named `file`.
    expect(body.get("file")).toBeInstanceOf(Blob);
    expect(body.get("audio")).toBeNull();
  });

  it("honors language and model overrides", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ text: "hello" }), { status: 200 })
    );
    await transcribe(new Blob(["a"], { type: "audio/webm" }), {
      language: "en",
      model: "turbo",
    });
    const body = fetchMock.mock.calls[0][1].body as FormData;
    expect(body.get("language")).toBe("en");
    expect(body.get("model")).toBe("turbo");
  });

  it("throws VoiceboxError on non-2xx", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("boom", { status: 500 })
    );
    await expect(
      transcribe(new Blob(["a"], { type: "audio/webm" }))
    ).rejects.toBeInstanceOf(VoiceboxError);
  });

  it("returns empty string when payload omits text", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({}), { status: 200 })
    );
    const result = await transcribe(new Blob(["a"], { type: "audio/webm" }));
    expect(result.text).toBe("");
  });
});

describe("synthesize", () => {
  it("posts JSON with qwen/ko defaults and profile_id, returns audio blob", async () => {
    const audioPayload = new Uint8Array([1, 2, 3]);
    fetchMock.mockResolvedValueOnce(
      new Response(audioPayload, {
        status: 200,
        headers: { "Content-Type": "audio/wav" },
      })
    );

    const blob = await synthesize("안녕", { profileId: "profile-x" });
    expect(blob).toBeInstanceOf(Blob);
    expect(blob.size).toBe(3);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/voice/generate");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
    const body = JSON.parse(init.body as string);
    expect(body).toMatchObject({
      profile_id: "profile-x",
      text: "안녕",
      engine: "qwen",
      language: "ko",
      model_size: "1.7B",
    });
    expect(body.voice_id).toBeUndefined();
  });

  it("honors engine + language + modelSize overrides", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(new Uint8Array([0]), { status: 200 })
    );
    await synthesize("hi", {
      profileId: "p",
      engine: "chatterbox",
      language: "en",
      modelSize: "0.6B",
    });
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.engine).toBe("chatterbox");
    expect(body.language).toBe("en");
    expect(body.model_size).toBe("0.6B");
  });

  it("throws VoiceboxError on 4xx", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("bad request", { status: 400 })
    );
    await expect(
      synthesize("hi", { profileId: "p" })
    ).rejects.toBeInstanceOf(VoiceboxError);
  });
});
