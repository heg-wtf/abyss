import { NextResponse } from "next/server";
import { getSystemStatus, getConfig } from "@/lib/cclaw";

export async function GET() {
  const status = getSystemStatus();
  const config = getConfig();

  return NextResponse.json({
    ...status,
    timezone: config?.timezone || "UTC",
    language: config?.language || "English",
    logLevel: config?.settings?.log_level || "INFO",
    commandTimeout: config?.settings?.command_timeout || 300,
  });
}
