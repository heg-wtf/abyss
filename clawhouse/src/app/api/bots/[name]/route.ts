import { NextRequest, NextResponse } from "next/server";
import {
  getBot,
  updateBot,
  getCronJobs,
  getBotSessions,
  getBotMemory,
  deleteSession,
} from "@/lib/cclaw";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  const bot = getBot(name);
  if (!bot) {
    return NextResponse.json({ error: "Bot not found" }, { status: 404 });
  }

  const cronJobs = getCronJobs(name);
  const sessions = getBotSessions(name);
  const memory = getBotMemory(name);

  return NextResponse.json({
    ...bot,
    telegram_token: "***",
    cronJobs,
    sessions,
    memory,
  });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  const { chatId } = await request.json();
  if (!chatId) {
    return NextResponse.json({ error: "chatId is required" }, { status: 400 });
  }
  const deleted = deleteSession(name, chatId);
  if (!deleted) {
    return NextResponse.json({ error: "Session not found" }, { status: 404 });
  }
  return NextResponse.json({ success: true });
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  const updates = await request.json();
  updateBot(name, updates);
  return NextResponse.json({ success: true });
}
