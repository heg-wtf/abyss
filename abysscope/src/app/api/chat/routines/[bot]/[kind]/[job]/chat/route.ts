import { NextRequest } from "next/server";
import { getApiBase } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Proxy the routine reply stream to the sidecar.
 *
 * Mirrors ``/api/chat/route.ts`` but the upstream path is the routine-
 * specific endpoint so the chat server can target the cron / heartbeat
 * session directory instead of a ``chat_<id>`` session. The body is
 * just ``{message: string}`` — no attachments, no session_id.
 */
export async function POST(
  request: NextRequest,
  context: { params: Promise<{ bot: string; kind: string; job: string }> },
) {
  const { bot, kind, job } = await context.params;
  if (kind !== "cron" && kind !== "heartbeat") {
    return Response.json({ error: "unknown routine kind" }, { status: 400 });
  }
  const upstream = await fetch(
    `${getApiBase()}/chat/routines/${encodeURIComponent(bot)}/${encodeURIComponent(kind)}/${encodeURIComponent(job)}/chat`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await request.text(),
    },
  );
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("content-type") ?? "text/event-stream",
      "Cache-Control": "no-cache",
    },
  });
}
