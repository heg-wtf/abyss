import { NextRequest } from "next/server";
import { VOICEBOX_BASE } from "@/lib/voicebox";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/voice/generate — JSON proxy to Voicebox `/api/generate`.
 *
 * Body: `{ text, voice_id?, engine?, language? }`. Returns audio binary
 * (Content-Type from upstream, typically `audio/wav` or `audio/mp3`).
 * Voicebox URL is hardcoded to localhost (SSRF guard).
 */
export async function POST(request: NextRequest) {
  let upstream: Response;
  try {
    upstream = await fetch(`${VOICEBOX_BASE}/api/generate`, {
      method: "POST",
      body: request.body,
      duplex: "half",
      headers: {
        "Content-Type": request.headers.get("Content-Type") ?? "application/json",
      },
      signal: request.signal,
    } as RequestInit & { duplex: "half" });
  } catch (error) {
    return Response.json(
      {
        error: "voicebox unreachable",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 503 }
    );
  }

  if (!upstream.ok) {
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
      },
    });
  }

  // Stream the binary audio body straight through.
  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "audio/wav",
      "Cache-Control": "no-store",
    },
  });
}
