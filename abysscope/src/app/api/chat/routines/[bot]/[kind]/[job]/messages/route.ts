import type { NextRequest } from "next/server";
import { getRoutineMessages, type RoutineSummary } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _request: NextRequest,
  context: {
    params: Promise<{ bot: string; kind: string; job: string }>;
  },
) {
  const { bot, kind, job } = await context.params;
  if (kind !== "cron" && kind !== "heartbeat") {
    return Response.json({ error: "unknown routine kind" }, { status: 400 });
  }
  try {
    const messages = await getRoutineMessages(
      bot,
      kind as RoutineSummary["kind"],
      job,
    );
    return Response.json({ messages });
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
