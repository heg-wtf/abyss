import type { NextRequest } from "next/server";
import { markSessionRead } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Proxy ``POST /api/chat/sessions/[bot]/[id]/read`` -> Python chat
 * server. Stamps ``last_read_at = now()`` on the session meta so the
 * list re-fetch shows ``unread=false``.
 */
export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ bot: string; id: string }> },
) {
  const { bot, id } = await params;
  try {
    await markSessionRead(bot, id);
    return Response.json({ ok: true });
  } catch (error) {
    return Response.json(
      {
        error: "chat sidecar unreachable",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 503 },
    );
  }
}
