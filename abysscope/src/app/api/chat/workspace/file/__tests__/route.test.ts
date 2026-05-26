import { afterEach, beforeEach, describe, expect, it } from "vitest";
import fs from "fs";
import os from "os";
import path from "path";
import yaml from "js-yaml";
import { NextRequest } from "next/server";
import { GET } from "../route";

let testHome: string;
const originalAbyssHome = process.env.ABYSS_HOME;

function writeYamlFile(filePath: string, data: unknown): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, yaml.dump(data), "utf-8");
}

function setupBot(): { workspace: string } {
  writeYamlFile(path.join(testHome, "config.yaml"), {
    bots: [{ name: "testbot", path: "bots/testbot" }],
    timezone: "UTC",
    language: "Korean",
    settings: { command_timeout: 120, log_level: "INFO" },
  });
  writeYamlFile(path.join(testHome, "bots", "testbot", "bot.yaml"), {
    display_name: "Test",
    personality: "p",
    role: "r",
    goal: "g",
    model: "sonnet",
    streaming: true,
    skills: [],
    allowed_users: [],
  });
  const workspace = path.join(
    testHome,
    "bots",
    "testbot",
    "sessions",
    "chat_1",
    "workspace",
  );
  fs.mkdirSync(workspace, { recursive: true });
  return { workspace };
}

function buildRequest(query: Record<string, string>): NextRequest {
  const params = new URLSearchParams(query);
  return new NextRequest(
    `http://localhost/api/chat/workspace/file?${params}`,
  );
}

beforeEach(() => {
  testHome = fs.mkdtempSync(path.join(os.tmpdir(), "workspace-file-route-"));
  process.env.ABYSS_HOME = testHome;
});

afterEach(() => {
  if (originalAbyssHome) process.env.ABYSS_HOME = originalAbyssHome;
  else delete process.env.ABYSS_HOME;
  fs.rmSync(testHome, { recursive: true, force: true });
});

describe("GET /api/chat/workspace/file", () => {
  it("returns 400 when path is missing", async () => {
    setupBot();
    const response = await GET(
      buildRequest({ bot: "testbot", session: "1" }),
    );
    expect(response.status).toBe(400);
  });

  it("returns 404 when bot is unknown", async () => {
    setupBot();
    const response = await GET(
      buildRequest({ bot: "ghost", session: "1", path: "plan.md" }),
    );
    expect(response.status).toBe(404);
  });

  it("returns 404 when file is missing", async () => {
    setupBot();
    const response = await GET(
      buildRequest({
        bot: "testbot",
        session: "1",
        path: "missing.md",
      }),
    );
    expect(response.status).toBe(404);
  });

  it("returns 400 when path points to a directory", async () => {
    const { workspace } = setupBot();
    fs.mkdirSync(path.join(workspace, "logs"));
    const response = await GET(
      buildRequest({ bot: "testbot", session: "1", path: "logs" }),
    );
    expect(response.status).toBe(400);
  });

  it("returns 200 with file content", async () => {
    const { workspace } = setupBot();
    fs.writeFileSync(
      path.join(workspace, "plan.md"),
      "# hello\n\nbody",
      "utf-8",
    );
    const response = await GET(
      buildRequest({ bot: "testbot", session: "1", path: "plan.md" }),
    );
    expect(response.status).toBe(200);
    const body = (await response.json()) as {
      content: string;
      size: number;
      truncated: boolean;
    };
    expect(body.content).toBe("# hello\n\nbody");
    expect(body.truncated).toBe(false);
    expect(body.size).toBe(13);
  });

  it("accepts session id with leading 'chat_' prefix", async () => {
    const { workspace } = setupBot();
    fs.writeFileSync(path.join(workspace, "note.md"), "hi", "utf-8");
    const response = await GET(
      buildRequest({
        bot: "testbot",
        session: "chat_1",
        path: "note.md",
      }),
    );
    expect(response.status).toBe(200);
    const body = (await response.json()) as { content: string };
    expect(body.content).toBe("hi");
  });

  it("returns 400 for path traversal attempts", async () => {
    setupBot();
    const response = await GET(
      buildRequest({
        bot: "testbot",
        session: "1",
        path: "../bot.yaml",
      }),
    );
    expect(response.status).toBe(400);
  });

  it("returns 403 when symlink escapes workspace", async () => {
    const { workspace } = setupBot();
    const outside = fs.mkdtempSync(
      path.join(os.tmpdir(), "outside-file-route-"),
    );
    try {
      fs.writeFileSync(path.join(outside, "secret.md"), "secret", "utf-8");
      fs.symlinkSync(
        path.join(outside, "secret.md"),
        path.join(workspace, "escape.md"),
      );
      const response = await GET(
        buildRequest({
          bot: "testbot",
          session: "1",
          path: "escape.md",
        }),
      );
      expect(response.status).toBe(403);
    } finally {
      fs.rmSync(outside, { recursive: true, force: true });
    }
  });
});
