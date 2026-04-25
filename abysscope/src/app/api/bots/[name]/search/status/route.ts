import { NextRequest, NextResponse } from "next/server";
import { getSearchStatus } from "@/lib/conversation-search";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  const status = getSearchStatus(name);
  return NextResponse.json(status);
}
