import type { NextRequest } from "next/server";
import { markRoutineRead, type RoutineSummary } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Proxy ``POST /api/chat/routines/[bot]/[kind]/[job]/read`` -> Python
 * chat server. See ``markSessionRead`` for the read-state model.
 */
export async function POST(
  _request: NextRequest,
  context: { params: Promise<{ bot: string; kind: string; job: string }> },
) {
  const { bot, kind, job } = await context.params;
  if (kind !== "cron" && kind !== "heartbeat") {
    return Response.json({ error: "unknown routine kind" }, { status: 400 });
  }
  try {
    await markRoutineRead(bot, kind as RoutineSummary["kind"], job);
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
