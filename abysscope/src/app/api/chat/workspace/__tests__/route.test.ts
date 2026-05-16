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
  return { workspace };
}

function buildRequest(query: Record<string, string>): NextRequest {
  const params = new URLSearchParams(query);
  return new NextRequest(`http://localhost/api/chat/workspace?${params}`);
}

beforeEach(() => {
  testHome = fs.mkdtempSync(path.join(os.tmpdir(), "workspace-route-"));
  process.env.ABYSS_HOME = testHome;
});

afterEach(() => {
  if (originalAbyssHome) process.env.ABYSS_HOME = originalAbyssHome;
  else delete process.env.ABYSS_HOME;
  fs.rmSync(testHome, { recursive: true, force: true });
});

describe("GET /api/chat/workspace", () => {
  it("returns 400 when bot is missing", async () => {
    const response = await GET(buildRequest({ session: "1" }));
    expect(response.status).toBe(400);
  });

  it("returns 400 when session is missing", async () => {
    const response = await GET(buildRequest({ bot: "testbot" }));
    expect(response.status).toBe(400);
  });

  it("returns 404 when bot is unknown", async () => {
    setupBot();
    const response = await GET(
      buildRequest({ bot: "ghost", session: "1" }),
    );
    expect(response.status).toBe(404);
  });

  it("returns 200 with empty tree when workspace is missing", async () => {
    setupBot();
    const response = await GET(
      buildRequest({ bot: "testbot", session: "1" }),
    );
    expect(response.status).toBe(200);
    const body = (await response.json()) as {
      missing: boolean;
      tree: unknown[];
    };
    expect(body.missing).toBe(true);
    expect(body.tree).toEqual([]);
  });

  it("returns 200 with tree when workspace has files", async () => {
    const { workspace } = setupBot();
    fs.mkdirSync(workspace, { recursive: true });
    fs.writeFileSync(path.join(workspace, "note.md"), "hi");
    fs.mkdirSync(path.join(workspace, "logs"));

    const response = await GET(
      buildRequest({ bot: "testbot", session: "1" }),
    );
    expect(response.status).toBe(200);
    const body = (await response.json()) as {
      tree: { name: string; type: string }[];
    };
    expect(body.tree.map((n) => `${n.type}:${n.name}`)).toEqual([
      "dir:logs",
      "file:note.md",
    ]);
  });

  it("returns 400 for path traversal attempts", async () => {
    const { workspace } = setupBot();
    fs.mkdirSync(workspace, { recursive: true });
    const response = await GET(
      buildRequest({ bot: "testbot", session: "1", path: ".." }),
    );
    expect(response.status).toBe(400);
  });

  it("returns 403 when symlink escapes workspace", async () => {
    const { workspace } = setupBot();
    fs.mkdirSync(workspace, { recursive: true });
    const outside = fs.mkdtempSync(path.join(os.tmpdir(), "outside-route-"));
    try {
      fs.symlinkSync(outside, path.join(workspace, "escape"));
      const response = await GET(
        buildRequest({ bot: "testbot", session: "1", path: "escape" }),
      );
      expect(response.status).toBe(403);
    } finally {
      fs.rmSync(outside, { recursive: true, force: true });
    }
  });
});
