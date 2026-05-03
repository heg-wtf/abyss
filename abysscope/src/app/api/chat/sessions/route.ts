import { NextRequest } from "next/server";
import {
  createChatSession,
  listChatSessions,
} from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const bot = request.nextUrl.searchParams.get("bot") ?? "";
  if (!bot) {
    return Response.json({ error: "bot required" }, { status: 400 });
  }
  try {
    const sessions = await listChatSessions(bot);
    return Response.json({ sessions });
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

export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => ({}))) as { bot?: string };
  if (!body.bot) {
    return Response.json({ error: "bot required" }, { status: 400 });
  }
  try {
    const session = await createChatSession(body.bot);
    return Response.json(session);
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
