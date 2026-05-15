import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { getBot, getAbyssHome } from "@/lib/abyss";

/**
 * Bot avatar — file-backed at ``~/.abyss/bots/<name>/avatar.jpg``.
 *
 * Earlier revisions fetched a fallback from Telegram via the bot's
 * ``telegram_token``. That dependency is gone — the dashboard now
 * owns avatar lifecycle directly via the edit page's upload field.
 *
 * GET serves the cached file (or 404 → the ``BotAvatar`` component
 * falls back to the colored initial). POST accepts a multipart
 * upload to replace the file. DELETE removes it. The on-disk filename
 * stays ``avatar.jpg`` regardless of source mime so older code that
 * points at that path keeps working.
 */

const ALLOWED_MIME = new Set(["image/jpeg", "image/png", "image/webp"]);
const MAX_BYTES = 2 * 1024 * 1024; // 2 MB
// Short cache so a freshly uploaded avatar reaches the rest of the
// dashboard within seconds.
const CACHE_CONTROL = "private, max-age=60, must-revalidate";

function getBotAvatarPath(botName: string): string {
  return path.join(getAbyssHome(), "bots", botName, "avatar.jpg");
}

function magicBytesOk(prefix: Buffer, declared: string): boolean {
  if (declared === "image/png")
    return prefix
      .slice(0, 8)
      .equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
  if (declared === "image/jpeg")
    return prefix[0] === 0xff && prefix[1] === 0xd8 && prefix[2] === 0xff;
  if (declared === "image/webp")
    return (
      prefix.slice(0, 4).toString("ascii") === "RIFF" &&
      prefix.slice(8, 12).toString("ascii") === "WEBP"
    );
  return false;
}

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  const bot = getBot(name);
  if (!bot) {
    return NextResponse.json({ error: "Bot not found" }, { status: 404 });
  }
  const avatarPath = getBotAvatarPath(name);
  if (!fs.existsSync(avatarPath)) {
    return NextResponse.json({ error: "No avatar" }, { status: 404 });
  }
  const stat = fs.statSync(avatarPath);
  const imageBuffer = fs.readFileSync(avatarPath);
  return new NextResponse(imageBuffer.buffer as ArrayBuffer, {
    headers: {
      "Content-Type": "image/jpeg",
      "Cache-Control": CACHE_CONTROL,
      ETag: `"${stat.mtimeMs}"`,
    },
  });
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  const bot = getBot(name);
  if (!bot) {
    return NextResponse.json({ error: "Bot not found" }, { status: 404 });
  }

  let formData: FormData;
  try {
    formData = await request.formData();
  } catch {
    return NextResponse.json({ error: "Invalid form data" }, { status: 400 });
  }

  const file = formData.get("avatar");
  if (!(file instanceof File)) {
    return NextResponse.json(
      { error: "avatar field is required (file)" },
      { status: 400 },
    );
  }
  if (!ALLOWED_MIME.has(file.type)) {
    return NextResponse.json(
      { error: `Unsupported type: ${file.type}. Use JPEG, PNG, or WebP.` },
      { status: 400 },
    );
  }
  if (file.size > MAX_BYTES) {
    return NextResponse.json(
      { error: `File too large (${file.size} bytes). Max 2 MB.` },
      { status: 413 },
    );
  }

  const arrayBuffer = await file.arrayBuffer();
  const buffer = Buffer.from(arrayBuffer);
  if (!magicBytesOk(buffer.subarray(0, 16), file.type)) {
    return NextResponse.json(
      { error: "File content does not match declared type." },
      { status: 400 },
    );
  }

  const avatarPath = getBotAvatarPath(name);
  fs.mkdirSync(path.dirname(avatarPath), { recursive: true });
  fs.writeFileSync(avatarPath, buffer);

  return NextResponse.json({ ok: true, bytes: buffer.length });
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params;
  const bot = getBot(name);
  if (!bot) {
    return NextResponse.json({ error: "Bot not found" }, { status: 404 });
  }
  const avatarPath = getBotAvatarPath(name);
  if (fs.existsSync(avatarPath)) {
    fs.unlinkSync(avatarPath);
  }
  return NextResponse.json({ ok: true });
}
