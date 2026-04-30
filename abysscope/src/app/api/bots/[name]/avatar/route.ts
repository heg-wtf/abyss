import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { getBot, getAbyssHome } from "@/lib/abyss";

const CACHE_MAX_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours

async function fetchTelegramAvatar(token: string): Promise<Buffer | null> {
  try {
    const baseUrl = `https://api.telegram.org/bot${token}`;

    const meResponse = await fetch(`${baseUrl}/getMe`, {
      signal: AbortSignal.timeout(10_000),
    });
    if (!meResponse.ok) return null;
    const meData = (await meResponse.json()) as { result?: { id?: number } };
    const botId = meData.result?.id;
    if (!botId) return null;

    const photosResponse = await fetch(
      `${baseUrl}/getUserProfilePhotos?user_id=${botId}&limit=1`,
      { signal: AbortSignal.timeout(10_000) },
    );
    if (!photosResponse.ok) return null;
    const photosData = (await photosResponse.json()) as {
      result?: { photos?: Array<Array<{ file_id: string }>> };
    };
    const photos = photosData.result?.photos;
    if (!photos || photos.length === 0) return null;

    // Use largest size (last in array)
    const photoSizes = photos[0];
    const bestPhoto = photoSizes[photoSizes.length - 1];
    if (!bestPhoto) return null;

    const fileResponse = await fetch(
      `${baseUrl}/getFile?file_id=${bestPhoto.file_id}`,
      { signal: AbortSignal.timeout(10_000) },
    );
    if (!fileResponse.ok) return null;
    const fileData = (await fileResponse.json()) as {
      result?: { file_path?: string };
    };
    const filePath = fileData.result?.file_path;
    if (!filePath) return null;

    const imageResponse = await fetch(
      `https://api.telegram.org/file/bot${token}/${filePath}`,
      { signal: AbortSignal.timeout(15_000) },
    );
    if (!imageResponse.ok) return null;

    const arrayBuffer = await imageResponse.arrayBuffer();
    return Buffer.from(arrayBuffer);
  } catch (err) {
    console.error(`[avatar] Telegram fetch failed: ${err}`);
    return null;
  }
}

function getBotAvatarPath(botName: string): string {
  return path.join(getAbyssHome(), "bots", botName, "avatar.jpg");
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  const bot = getBot(name);
  if (!bot) {
    return NextResponse.json({ error: "Bot not found" }, { status: 404 });
  }

  const forceRefresh = request.nextUrl.searchParams.get("refresh") === "1";
  const avatarPath = getBotAvatarPath(name);

  // Serve cache if fresh
  if (!forceRefresh && fs.existsSync(avatarPath)) {
    const stat = fs.statSync(avatarPath);
    if (Date.now() - stat.mtimeMs < CACHE_MAX_AGE_MS) {
      const imageBuffer = fs.readFileSync(avatarPath);
      return new NextResponse(imageBuffer.buffer as ArrayBuffer, {
        headers: {
          "Content-Type": "image/jpeg",
          "Cache-Control": "public, max-age=86400",
        },
      });
    }
  }

  // Fetch from Telegram
  const imageBuffer = await fetchTelegramAvatar(bot.telegram_token);
  if (!imageBuffer) {
    // Serve stale cache if Telegram fetch fails
    if (fs.existsSync(avatarPath)) {
      const staleBuffer = fs.readFileSync(avatarPath);
      return new NextResponse(staleBuffer.buffer as ArrayBuffer, {
        headers: {
          "Content-Type": "image/jpeg",
          "Cache-Control": "public, max-age=3600",
        },
      });
    }
    return NextResponse.json({ error: "No avatar available" }, { status: 404 });
  }

  // Cache to disk
  fs.writeFileSync(avatarPath, imageBuffer);

  return new NextResponse(imageBuffer.buffer as ArrayBuffer, {
    headers: {
      "Content-Type": "image/jpeg",
      "Cache-Control": "public, max-age=86400",
    },
  });
}
