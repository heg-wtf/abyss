import { NextResponse } from "next/server";
import { listBots, getCronJobs, getBotSessions } from "@/lib/cclaw";

export async function GET() {
  const bots = listBots();
  const botsWithMeta = bots.map((bot) => {
    const cronJobs = getCronJobs(bot.name);
    const sessions = getBotSessions(bot.name);
    const lastActivity = sessions
      .map((s) => s.lastActivity)
      .filter(Boolean)
      .sort((a, b) => (b?.getTime() || 0) - (a?.getTime() || 0))[0];

    return {
      ...bot,
      telegram_token: "***",
      cronJobCount: cronJobs.length,
      sessionCount: sessions.length,
      lastActivity: lastActivity?.toISOString() || null,
    };
  });

  return NextResponse.json(botsWithMeta);
}
