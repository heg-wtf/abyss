import { NextRequest, NextResponse } from "next/server";
import { exec } from "child_process";
import fs from "fs";
import { getCclawHome } from "@/lib/cclaw";

export async function POST(request: NextRequest) {
  const { path: targetPath } = await request.json();

  if (!targetPath || typeof targetPath !== "string") {
    return NextResponse.json({ error: "Path is required" }, { status: 400 });
  }

  const cclawHome = getCclawHome();
  const resolvedPath = targetPath.startsWith("/")
    ? targetPath
    : `${cclawHome}/${targetPath}`;

  if (!resolvedPath.startsWith(cclawHome)) {
    return NextResponse.json(
      { error: "Path must be within cclaw home" },
      { status: 403 },
    );
  }

  if (!fs.existsSync(resolvedPath)) {
    return NextResponse.json({ error: "Path not found" }, { status: 404 });
  }

  exec(`open "${resolvedPath}"`, (error) => {
    if (error) console.error("Failed to open Finder:", error.message);
  });
  return NextResponse.json({ ok: true });
}
