import { NextRequest } from "next/server";
import { deleteChatSession } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ bot: string; id: string }> }
) {
  const { bot, id } = await params;
  try {
    await deleteChatSession(bot, id);
    return Response.json({ deleted: true });
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
