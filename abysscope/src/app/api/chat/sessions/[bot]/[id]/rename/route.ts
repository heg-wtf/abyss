import { NextRequest } from "next/server";
import { renameChatSession } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Proxy ``POST /api/chat/sessions/[bot]/[id]/rename`` -> Python chat
 * server. The sidecar enforces length + control-character cleanup.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ bot: string; id: string }> }
) {
  const { bot, id } = await params;
  let body: { name?: unknown };
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "invalid JSON body" }, { status: 400 });
  }

  if (typeof body.name !== "string") {
    return Response.json(
      { error: "name must be a string" },
      { status: 400 }
    );
  }

  try {
    const result = await renameChatSession(bot, id, body.name);
    return Response.json(result);
  } catch (error) {
    return Response.json(
      {
        error: "chat sidecar unreachable",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 503 }
    );
  }
}
