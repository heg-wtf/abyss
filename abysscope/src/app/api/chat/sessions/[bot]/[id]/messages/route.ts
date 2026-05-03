import { NextRequest } from "next/server";
import { getChatMessages } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ bot: string; id: string }> }
) {
  const { bot, id } = await params;
  try {
    const messages = await getChatMessages(bot, id);
    return Response.json({ messages });
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
