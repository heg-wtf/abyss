import { NextRequest, NextResponse } from "next/server";
import {
  readBotWorkspaceFile,
  WorkspaceAccessError,
} from "@/lib/abyss";

/**
 * Inline preview endpoint for a single workspace file.
 *
 * Used by the chat workspace side panel to render markdown plans /
 * logs without opening them in Finder. Reuses the same root +
 * symlink guards as the tree listing.
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const bot = searchParams.get("bot");
  const session = searchParams.get("session");
  const relativePath = searchParams.get("path") ?? "";

  if (!bot || !session || !relativePath) {
    return NextResponse.json(
      { error: "bot, session, and path are required" },
      { status: 400 },
    );
  }

  try {
    const result = readBotWorkspaceFile(bot, session, relativePath);
    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof WorkspaceAccessError) {
      const status =
        error.code === "not_found"
          ? 404
          : error.code === "forbidden"
            ? 403
            : 400;
      return NextResponse.json({ error: error.message }, { status });
    }
    const message = error instanceof Error ? error.message : String(error);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
