import { getApiBase } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Proxy ``POST /api/bots/new`` -> Python sidecar ``POST /chat/bots``.
 *
 * The browser hits this Next.js route rather than the sidecar
 * directly because on a phone ``127.0.0.1`` resolves to the phone
 * itself, not the Mac running ``abyss start``. The sidecar speaks
 * the actual ``onboarding.create_bot`` flow and writes
 * ``bot.yaml`` + the ``config.yaml`` entry on disk.
 */
export async function POST(request: Request) {
  try {
    const body = await request.json();
    const response = await fetch(getApiBase() + "/chat/bots", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    return Response.json(payload, { status: response.status });
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
