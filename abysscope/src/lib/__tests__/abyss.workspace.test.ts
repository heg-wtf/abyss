import { afterEach, beforeEach, describe, expect, it } from "vitest";
import fs from "fs";
import os from "os";
import path from "path";
import yaml from "js-yaml";
import {
  listBotWorkspaceTree,
  WorkspaceAccessError,
} from "../abyss";

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
    "chat_42",
    "workspace",
  );
  return { workspace };
}

beforeEach(() => {
  testHome = fs.mkdtempSync(path.join(os.tmpdir(), "workspace-test-"));
  process.env.ABYSS_HOME = testHome;
});

afterEach(() => {
  if (originalAbyssHome) process.env.ABYSS_HOME = originalAbyssHome;
  else delete process.env.ABYSS_HOME;
  fs.rmSync(testHome, { recursive: true, force: true });
});

describe("listBotWorkspaceTree", () => {
  it("returns missing=true when workspace directory does not exist", () => {
    setupBot();
    const result = listBotWorkspaceTree("testbot", "42");
    expect(result.missing).toBe(true);
    expect(result.tree).toEqual([]);
  });

  it("lists files and directories with dir-first sorting", () => {
    const { workspace } = setupBot();
    fs.mkdirSync(workspace, { recursive: true });
    fs.writeFileSync(path.join(workspace, "zzz.txt"), "z");
    fs.writeFileSync(path.join(workspace, "aaa.md"), "a");
    fs.mkdirSync(path.join(workspace, "subdir"));
    fs.mkdirSync(path.join(workspace, "alpha"));

    const result = listBotWorkspaceTree("testbot", "42");
    expect(result.missing).toBe(false);
    expect(result.tree.map((node) => `${node.type}:${node.name}`)).toEqual([
      "dir:alpha",
      "dir:subdir",
      "file:aaa.md",
      "file:zzz.txt",
    ]);
    const file = result.tree.find((node) => node.name === "aaa.md");
    expect(file?.size).toBe(1);
    expect(file?.mtime).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it("returns depth-1 only; nested directories have no children field", () => {
    const { workspace } = setupBot();
    fs.mkdirSync(path.join(workspace, "outer", "inner"), { recursive: true });
    fs.writeFileSync(path.join(workspace, "outer", "leaf.txt"), "x");

    const result = listBotWorkspaceTree("testbot", "42");
    const outer = result.tree.find((node) => node.name === "outer");
    expect(outer?.type).toBe("dir");
    expect(outer?.children).toBeUndefined();
  });

  it("lists children when relativePath is provided", () => {
    const { workspace } = setupBot();
    fs.mkdirSync(path.join(workspace, "nested"), { recursive: true });
    fs.writeFileSync(path.join(workspace, "nested", "child.txt"), "c");

    const result = listBotWorkspaceTree("testbot", "42", "nested");
    expect(result.tree.map((n) => n.name)).toEqual(["child.txt"]);
    expect(result.tree[0].path).toBe(path.join("nested", "child.txt"));
  });

  it("rejects path traversal", () => {
    const { workspace } = setupBot();
    fs.mkdirSync(workspace, { recursive: true });
    expect(() => listBotWorkspaceTree("testbot", "42", "..")).toThrow(
      WorkspaceAccessError,
    );
    expect(() => listBotWorkspaceTree("testbot", "42", "foo/../..")).toThrow(
      WorkspaceAccessError,
    );
  });

  it("rejects absolute paths", () => {
    const { workspace } = setupBot();
    fs.mkdirSync(workspace, { recursive: true });
    expect(() => listBotWorkspaceTree("testbot", "42", "/etc")).toThrow(
      WorkspaceAccessError,
    );
  });

  it("rejects NUL byte in path", () => {
    const { workspace } = setupBot();
    fs.mkdirSync(workspace, { recursive: true });
    expect(() => listBotWorkspaceTree("testbot", "42", "foo\0bar")).toThrow(
      WorkspaceAccessError,
    );
  });

  it("rejects symlinks that escape the workspace root", () => {
    const { workspace } = setupBot();
    fs.mkdirSync(workspace, { recursive: true });
    const outside = fs.mkdtempSync(path.join(os.tmpdir(), "outside-"));
    try {
      fs.symlinkSync(outside, path.join(workspace, "escape"));
      expect(() => listBotWorkspaceTree("testbot", "42", "escape")).toThrow(
        WorkspaceAccessError,
      );
    } finally {
      fs.rmSync(outside, { recursive: true, force: true });
    }
  });

  it("throws not_found for unknown bot", () => {
    setupBot();
    try {
      listBotWorkspaceTree("ghostbot", "42");
      throw new Error("expected throw");
    } catch (error) {
      expect(error).toBeInstanceOf(WorkspaceAccessError);
      expect((error as WorkspaceAccessError).code).toBe("not_found");
    }
  });

  it("rejects chatId with unsafe characters", () => {
    setupBot();
    try {
      listBotWorkspaceTree("testbot", "../etc");
      throw new Error("expected throw");
    } catch (error) {
      expect(error).toBeInstanceOf(WorkspaceAccessError);
      expect((error as WorkspaceAccessError).code).toBe("not_found");
    }
  });

  it("throws not_found when relative target does not exist", () => {
    const { workspace } = setupBot();
    fs.mkdirSync(workspace, { recursive: true });
    try {
      listBotWorkspaceTree("testbot", "42", "missing");
      throw new Error("expected throw");
    } catch (error) {
      expect(error).toBeInstanceOf(WorkspaceAccessError);
      expect((error as WorkspaceAccessError).code).toBe("not_found");
    }
  });
});
