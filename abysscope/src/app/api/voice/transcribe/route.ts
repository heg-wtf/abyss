import { NextRequest } from "next/server";
import { VOICEBOX_BASE } from "@/lib/voicebox";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/voice/transcribe — multipart proxy to Voicebox `/captures`.
 *
 * Voicebox v0.5.0's `/transcribe` endpoint is currently broken on Apple
 * Silicon ("There is no Stream(gpu, N) in current thread."), so we route
 * through `/captures` which uses the same Whisper backend via the
 * dictation pipeline. We rebuild the multipart so the field name maps to
 * `/captures` (`stt_model` instead of `model`) and shape the response back
 * to `{ text, duration }` to keep the client API stable.
 */
export async function POST(request: NextRequest) {
  let inboundForm: FormData;
  try {
    inboundForm = await request.formData();
  } catch (error) {
    return Response.json(
      {
        error: "invalid multipart body",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 400 }
    );
  }

  const file = inboundForm.get("file");
  if (!(file instanceof Blob)) {
    return Response.json(
      { error: "missing audio file" },
      { status: 400 }
    );
  }
  const language = (inboundForm.get("language") as string | null) ?? undefined;
  const model = (inboundForm.get("model") as string | null) ?? undefined;

  const upstreamForm = new FormData();
  upstreamForm.append(
    "file",
    file,
    typeof (file as File).name === "string" ? (file as File).name : "recording.webm"
  );
  // Voicebox /captures accepts source ∈ {dictation, file, recording}.
  upstreamForm.append("source", "recording");
  if (language) upstreamForm.append("language", language);
  if (model) upstreamForm.append("stt_model", model);

  let upstream: Response;
  try {
    upstream = await fetch(`${VOICEBOX_BASE}/captures`, {
      method: "POST",
      body: upstreamForm,
      signal: request.signal,
    });
  } catch (error) {
    return Response.json(
      {
        error: "voicebox unreachable",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 503 }
    );
  }

  if (!upstream.ok) {
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
      },
    });
  }

  const payload = (await upstream.json()) as {
    transcript_raw?: string;
    transcript_refined?: string | null;
    duration_ms?: number;
  };
  const text = payload.transcript_refined?.trim() || payload.transcript_raw || "";
  const duration =
    typeof payload.duration_ms === "number" ? payload.duration_ms / 1000 : undefined;

  return Response.json({ text, duration });
}
