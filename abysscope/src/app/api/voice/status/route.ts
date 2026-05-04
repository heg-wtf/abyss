import { VOICEBOX_BASE, HEALTH_TIMEOUT_MS } from "@/lib/voicebox";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/voice/status — probe the local Voicebox API server.
 *
 * Voicebox runs at a fixed localhost URL (SSRF guard — never derived from
 * user input). Returns `{ ok: true }` when reachable, otherwise `{ ok: false }`
 * with status 503.
 */
export async function GET() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
  try {
    const upstream = await fetch(`${VOICEBOX_BASE}/api/status`, {
      method: "GET",
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (!upstream.ok) {
      return Response.json({ ok: false }, { status: 503 });
    }
    return Response.json({ ok: true });
  } catch {
    clearTimeout(timer);
    return Response.json({ ok: false }, { status: 503 });
  }
}
