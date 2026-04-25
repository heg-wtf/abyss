import { NextRequest, NextResponse } from "next/server";
import { reindexBot } from "@/lib/conversation-search";

export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  const result = await reindexBot(name);
  return NextResponse.json(result, { status: result.ok ? 200 : 500 });
}
