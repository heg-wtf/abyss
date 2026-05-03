import { NextRequest } from "next/server";
import { getApiBase } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/chat/upload — proxy multipart attachment uploads to the sidecar.
 *
 * The browser sends a `FormData` payload (`bot`, `session_id`, `file`). We
 * stream it verbatim to the abyss chat server's `/chat/upload` endpoint and
 * forward the JSON response (including 4xx errors like `invalid_mime`,
 * `too_many_uploads`).
 */
export async function POST(request: NextRequest) {
  let upstream: Response;
  try {
    upstream = await fetch(getApiBase() + "/chat/upload", {
      method: "POST",
      // Pass the original multipart body untouched (Content-Type + boundary).
      body: request.body,
      // Required when forwarding a streaming `ReadableStream` body.
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
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
    },
  });
}
