import { NextRequest, NextResponse } from "next/server";
import { searchMessages } from "@/lib/conversation-search";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  const url = new URL(request.url);
  const query = url.searchParams.get("q") ?? "";
  const limitParam = url.searchParams.get("limit");
  const limit = limitParam ? Number(limitParam) : 30;
  if (!query.trim()) {
    return NextResponse.json({ hits: [] });
  }
  try {
    const hits = searchMessages(name, query, Number.isFinite(limit) ? limit : 30);
    return NextResponse.json({ hits });
  } catch (error) {
    return NextResponse.json(
      { hits: [], error: error instanceof Error ? error.message : String(error) },
      { status: 500 },
    );
  }
}
