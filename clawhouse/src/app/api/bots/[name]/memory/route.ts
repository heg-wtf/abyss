import { NextRequest, NextResponse } from "next/server";
import { getBotMemory, updateBotMemory } from "@/lib/cclaw";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  const memory = getBotMemory(name);
  return NextResponse.json({ content: memory });
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  const { content } = await request.json();
  updateBotMemory(name, content);
  return NextResponse.json({ success: true });
}
