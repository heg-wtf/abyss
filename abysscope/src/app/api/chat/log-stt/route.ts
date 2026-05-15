import { getApiBase } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Proxy ``POST /api/chat/log-stt`` -> Python sidecar
 * ``POST /chat/log-stt``.
 *
 * The browser fires this fire-and-forget when Scribe v2 realtime
 * emits a connect / commit / disconnect / error event. The sidecar
 * logs the metadata next to the rest of the abyss chat trace so
 * STT activity is visible in ``~/.abyss/logs/abyss-YYMMDD.log``
 * even though the audio bytes themselves go straight from the
 * browser to ElevenLabs over WebSocket.
 */
export async function POST(request: Request) {
  try {
    const body = await request.json();
    const response = await fetch(getApiBase() + "/chat/log-stt", {
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
