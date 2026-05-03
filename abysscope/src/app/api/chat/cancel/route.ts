import { NextRequest } from "next/server";
import { getApiBase } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = await request.text();
  try {
    const upstream = await fetch(getApiBase() + "/chat/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    return new Response(
      JSON.stringify({
        error: "chat sidecar unreachable",
        detail: error instanceof Error ? error.message : String(error),
      }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
}
