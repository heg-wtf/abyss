import { NextRequest } from "next/server";
import { VOICEBOX_BASE } from "@/lib/voicebox";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/voice/transcribe — multipart proxy to Voicebox `/transcribe`.
 *
 * Forwards the original `FormData` payload (file + language + model)
 * untouched. Voicebox URL is hardcoded to localhost (SSRF guard).
 */
export async function POST(request: NextRequest) {
  let upstream: Response;
  try {
    upstream = await fetch(`${VOICEBOX_BASE}/transcribe`, {
      method: "POST",
      body: request.body,
      duplex: "half",
      headers: {
        "Content-Type": request.headers.get("Content-Type") ?? "multipart/form-data",
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

  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
    },
  });
}
