import { checkHealth } from "@/lib/abyss-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const ok = await checkHealth();
  return Response.json({ ok }, { status: ok ? 200 : 503 });
}
