import { getApiBase } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Proxy ``GET /api/push/vapid-key`` -> Python chat server. Client
 * components hit this endpoint instead of ``127.0.0.1:3848`` because
 * a phone's loopback is the phone, not the Mac.
 */
export async function GET() {
  try {
    const response = await fetch(getApiBase() + "/chat/push/vapid-key", {
      method: "GET",
    });
    if (!response.ok) {
      return Response.json({ error: "vapid-key fetch failed" }, { status: 503 });
    }
    return Response.json(await response.json());
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
