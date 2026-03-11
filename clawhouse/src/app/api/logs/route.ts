import { NextRequest, NextResponse } from "next/server";
import { listLogFiles, getLogContent } from "@/lib/cclaw";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const file = searchParams.get("file");

  if (file) {
    const offset = parseInt(searchParams.get("offset") || "0", 10);
    const limit = parseInt(searchParams.get("limit") || "500", 10);
    const result = getLogContent(file, offset, limit);
    return NextResponse.json(result);
  }

  const files = listLogFiles();
  return NextResponse.json({ files });
}
