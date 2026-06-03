import { getApiBase } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Catch-all proxy from the browser to the abyss chat sidecar.
 *
 * The sidecar binds to 127.0.0.1:3848 (loopback only) so any browser
 * loading the dashboard over a non-loopback host (network IP, mDNS,
 * PWA over Tailscale) cannot reach it directly. This proxy keeps the
 * request same-origin: the browser hits the Next.js server, which
 * forwards the call to chat_server from inside the Mac.
 *
 * Body, query string, and HTTP status round-trip 1:1. Only the
 * Content-Type header is forwarded — chat_server does not consume
 * auth headers or cookies, and forwarding them indiscriminately
 * would leak browser context to the sidecar.
 *
 * Returns 503 on connect failure (matches the per-endpoint proxies
 * under ``/api/chat/*`` so the dashboard renders a consistent error).
 */
async function forward(
  req: Request,
  ctx: { params: Promise<{ path: string[] }> },
) {
  const { path } = await ctx.params;
  const upstreamPath = "/" + path.join("/");
  const upstream = new URL(getApiBase() + upstreamPath);
  const incoming = new URL(req.url);
  incoming.searchParams.forEach((value, key) => {
    upstream.searchParams.append(key, value);
  });

  const init: RequestInit = { method: req.method };
  const contentType = req.headers.get("content-type");
  if (contentType) {
    init.headers = { "content-type": contentType };
  }
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.text();
  }

  try {
    const response = await fetch(upstream, init);
    const body = await response.text();
    const headers = new Headers();
    const responseContentType = response.headers.get("content-type");
    if (responseContentType) {
      headers.set("content-type", responseContentType);
    }
    return new Response(body, { status: response.status, headers });
  } catch (error) {
    return Response.json(
      {
        error: "sidecar unreachable",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 503 },
    );
  }
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const DELETE = forward;
export const PATCH = forward;
