import { NextRequest } from "next/server";
import { getApiBase } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/chat/transcribe — proxy multipart audio to the sidecar STT endpoint.
 * Returns { text: string }.
 */
export async function POST(request: NextRequest) {
  let upstream: Response;
  try {
    upstream = await fetch(getApiBase() + "/chat/transcribe", {
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
        error: "chat sidecar unreachable",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 503 }
    );
  }

  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
  });
}
