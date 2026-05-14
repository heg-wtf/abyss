import type { NextRequest } from "next/server";
import { getApiBase } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "invalid JSON" }, { status: 400 });
  }

  try {
    const response = await fetch(getApiBase() + "/chat/push/visibility", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      // The browser uses ``keepalive`` so a tab-close ping still
      // completes — Node fetch supports it the same way.
      keepalive: true,
    });
    const data = await response.json().catch(() => ({}));
    return Response.json(data, { status: response.status });
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
