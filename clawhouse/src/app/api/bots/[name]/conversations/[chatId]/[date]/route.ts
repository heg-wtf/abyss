import { NextRequest, NextResponse } from "next/server";
import { getConversation } from "@/lib/cclaw";

export async function GET(
  _request: NextRequest,
  {
    params,
  }: { params: Promise<{ name: string; chatId: string; date: string }> },
) {
  const { name, chatId, date } = await params;
  const content = getConversation(name, chatId, date);
  return NextResponse.json({ content });
}
