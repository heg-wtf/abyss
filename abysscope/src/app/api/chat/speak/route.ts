import { NextRequest } from "next/server";
import { getApiBase } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/chat/speak — proxy TTS request to the sidecar and stream MP3 back.
 * Body: { text: string, voice_id?: string }
 */
export async function POST(request: NextRequest) {
  let upstream: Response;
  try {
    upstream = await fetch(getApiBase() + "/chat/speak", {
      method: "POST",
      body: request.body,
      duplex: "half",
      headers: { "Content-Type": "application/json" },
      signal: request.signal,
    } as RequestInit & { duplex: "half" });
  } catch (error) {
    return Response.json(
      {
        error: "chat sidecar unreachable",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 503 }
    );
  }

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "audio/mpeg",
      "Cache-Control": "no-store",
    },
  });
}
