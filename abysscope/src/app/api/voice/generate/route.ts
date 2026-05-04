import { NextRequest } from "next/server";
import { VOICEBOX_BASE } from "@/lib/voicebox";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/voice/generate — JSON proxy to Voicebox `/generate/stream`.
 *
 * Body: `GenerationRequest` JSON — `{ profile_id, text, language, engine?,
 * model_size? }`. Returns audio binary (typically `audio/wav`). Voicebox URL
 * is hardcoded to localhost (SSRF guard).
 *
 * `/generate/stream` returns audio synchronously without persisting the
 * generation, which suits the dashboard chat path where we just want to play
 * the result and discard.
 */
export async function POST(request: NextRequest) {
  let upstream: Response;
  try {
    upstream = await fetch(`${VOICEBOX_BASE}/generate/stream`, {
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

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "audio/wav",
      "Cache-Control": "no-store",
    },
  });
}
