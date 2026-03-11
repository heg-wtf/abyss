import { NextRequest, NextResponse } from "next/server";
import { getConfig, updateConfig } from "@/lib/cclaw";

export async function GET() {
  const config = getConfig();
  if (!config) {
    return NextResponse.json({ error: "Config not found" }, { status: 404 });
  }
  return NextResponse.json(config);
}

export async function PUT(request: NextRequest) {
  const updates = await request.json();
  updateConfig(updates);
  return NextResponse.json({ success: true });
}
