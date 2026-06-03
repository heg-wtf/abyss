import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET, POST, PUT, DELETE, PATCH } from "../sidecar/[...path]/route";
import { asParams, makeRequest } from "./_setup";

/**
 * The sidecar proxy is a Next.js route that forwards every request to
 * the abyss chat sidecar at ``getApiBase()`` (loopback). Tests mock
 * the global ``fetch`` so we never need a live sidecar.
 */

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function okResponse(body: unknown, contentType = "application/json"): Response {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status: 200,
    headers: { "content-type": contentType },
  });
}

describe("sidecar catch-all proxy", () => {
  it("GET forwards method + path + query string and mirrors status/body", async () => {
    fetchMock.mockResolvedValue(okResponse({ bot: "anne", facts: [] }));

    const req = makeRequest("/api/sidecar/facts/anne?subject=release&limit=5", {
      method: "GET",
    });
    const resp = await GET(req, { params: asParams({ path: ["facts", "anne"] }) });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [upstreamUrl, init] = fetchMock.mock.calls[0];
    expect(String(upstreamUrl)).toBe(
      "http://127.0.0.1:3848/facts/anne?subject=release&limit=5",
    );
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();

    expect(resp.status).toBe(200);
    const body = await resp.json();
    expect(body).toEqual({ bot: "anne", facts: [] });
  });

  it("POST forwards body + content-type and round-trips response", async () => {
    fetchMock.mockResolvedValue(
      okResponse({ ok: true, goal: { id: "smoke-test" } }),
    );

    const req = makeRequest("/api/sidecar/goals/anne", {
      method: "POST",
      json: { title: "Smoke test" },
    });
    const resp = await POST(req, { params: asParams({ path: ["goals", "anne"] }) });

    const [upstreamUrl, init] = fetchMock.mock.calls[0];
    expect(String(upstreamUrl)).toBe("http://127.0.0.1:3848/goals/anne");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "content-type": "application/json" });
    expect(init.body).toBe(JSON.stringify({ title: "Smoke test" }));

    expect(resp.status).toBe(200);
    const body = await resp.json();
    expect(body.goal.id).toBe("smoke-test");
  });

  it("PUT forwards method + nested path segments", async () => {
    fetchMock.mockResolvedValue(okResponse({ ok: true }));

    const req = makeRequest("/api/sidecar/facts/anne/42", {
      method: "PUT",
      json: { action: "retract" },
    });
    const resp = await PUT(req, {
      params: asParams({ path: ["facts", "anne", "42"] }),
    });

    const [upstreamUrl, init] = fetchMock.mock.calls[0];
    expect(String(upstreamUrl)).toBe("http://127.0.0.1:3848/facts/anne/42");
    expect(init.method).toBe("PUT");
    expect(resp.status).toBe(200);
  });

  it("DELETE forwards without body", async () => {
    fetchMock.mockResolvedValue(okResponse({ ok: true, goal_id: "x" }));

    const req = makeRequest("/api/sidecar/goals/anne/x", { method: "DELETE" });
    const resp = await DELETE(req, {
      params: asParams({ path: ["goals", "anne", "x"] }),
    });

    const [upstreamUrl, init] = fetchMock.mock.calls[0];
    expect(String(upstreamUrl)).toBe("http://127.0.0.1:3848/goals/anne/x");
    expect(init.method).toBe("DELETE");
    // DELETE may carry an empty body — fetch ignores it but we never
    // synthesise content. Either undefined or "" is acceptable.
    expect(init.body == null || init.body === "").toBe(true);
    expect(resp.status).toBe(200);
  });

  it("PATCH is wired even though no current endpoint uses it", async () => {
    fetchMock.mockResolvedValue(okResponse({ ok: true }));

    const req = makeRequest("/api/sidecar/anything", { method: "PATCH" });
    const resp = await PATCH(req, { params: asParams({ path: ["anything"] }) });

    expect(resp.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("propagates upstream non-2xx status + body", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: "bot not found" }), {
        status: 404,
        headers: { "content-type": "application/json" },
      }),
    );

    const req = makeRequest("/api/sidecar/facts/ghost", { method: "GET" });
    const resp = await GET(req, { params: asParams({ path: ["facts", "ghost"] }) });

    expect(resp.status).toBe(404);
    const body = await resp.json();
    expect(body).toEqual({ error: "bot not found" });
  });

  it("returns 503 when the sidecar is unreachable", async () => {
    fetchMock.mockRejectedValue(new Error("ECONNREFUSED"));

    const req = makeRequest("/api/sidecar/facts/anne", { method: "GET" });
    const resp = await GET(req, { params: asParams({ path: ["facts", "anne"] }) });

    expect(resp.status).toBe(503);
    const body = await resp.json();
    expect(body.error).toBe("sidecar unreachable");
    expect(body.detail).toBe("ECONNREFUSED");
  });

  it("does not forward auth-bearing headers (only content-type passes through)", async () => {
    fetchMock.mockResolvedValue(okResponse({ ok: true }));

    const req = makeRequest("/api/sidecar/anything", {
      method: "POST",
      json: { x: 1 },
      headers: {
        Authorization: "Bearer secret",
        Cookie: "session=secret",
      },
    });
    await POST(req, { params: asParams({ path: ["anything"] }) });

    const [, init] = fetchMock.mock.calls[0];
    const forwarded = init.headers as Record<string, string>;
    expect(Object.keys(forwarded)).toEqual(["content-type"]);
    expect(forwarded.authorization).toBeUndefined();
    expect(forwarded.cookie).toBeUndefined();
  });
});
