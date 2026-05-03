import { NextRequest } from "next/server";
import { getApiBase } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/chat/sessions/<bot>/<id>/file/<name> — proxy a previously
 * uploaded attachment back to the browser. Forwards the upstream
 * `Content-Type` so images render inline and PDFs preview natively.
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ bot: string; id: string; name: string }> }
) {
  const { bot, id, name } = await params;
  const url = `${getApiBase()}/chat/sessions/${encodeURIComponent(bot)}/${encodeURIComponent(id)}/file/${encodeURIComponent(name)}`;
  let upstream: Response;
  try {
    upstream = await fetch(url);
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
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
      },
    });
  }

  const headers: Record<string, string> = {
    "Content-Type": upstream.headers.get("Content-Type") ?? "application/octet-stream",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "private, max-age=300",
  };
  const disposition = upstream.headers.get("Content-Disposition");
  if (disposition) headers["Content-Disposition"] = disposition;

  return new Response(upstream.body, {
    status: 200,
    headers,
  });
}
