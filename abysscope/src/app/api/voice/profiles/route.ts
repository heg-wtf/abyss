import { VOICEBOX_BASE } from "@/lib/voicebox";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * GET /api/voice/profiles — proxy to Voicebox `/profiles`.
 *
 * Returns the list of voice profiles available to the local Voicebox. The
 * dashboard auto-picks the first profile for synthesis; if empty, the Voice
 * button surfaces a hint to create one in the Voicebox UI.
 */
export async function GET() {
  let upstream: Response;
  try {
    upstream = await fetch(`${VOICEBOX_BASE}/profiles`, { method: "GET" });
  } catch (error) {
    return Response.json(
      {
        error: "voicebox unreachable",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 503 }
    );
  }

  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
    },
  });
}
