import { NextRequest } from "next/server";
import { getApiBase } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const upstream = await fetch(getApiBase() + "/chat/scribe-token", {
      method: "POST",
      signal: request.signal,
    });
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
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
