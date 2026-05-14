import type { NextRequest } from "next/server";
import { getApiBase } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function forward(request: NextRequest, method: "POST" | "DELETE") {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "invalid JSON" }, { status: 400 });
  }

  try {
    const response = await fetch(getApiBase() + "/chat/push/subscribe", {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
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

export async function POST(request: NextRequest) {
  return forward(request, "POST");
}

export async function DELETE(request: NextRequest) {
  return forward(request, "DELETE");
}
