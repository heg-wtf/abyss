import fs from "fs";
import path from "path";
import { getBotPath } from "./bots";

export interface WorkspaceTreeNode {
  name: string;
  path: string;
  type: "file" | "dir";
  size?: number;
  mtime: string;
  children?: WorkspaceTreeNode[];
}

export interface WorkspaceTreeResult {
  root: string;
  relativePath: string;
  tree: WorkspaceTreeNode[];
  missing: boolean;
}

export class WorkspaceAccessError extends Error {
  constructor(
    message: string,
    public readonly code: "invalid_path" | "not_found" | "forbidden",
  ) {
    super(message);
    this.name = "WorkspaceAccessError";
  }
}

function workspaceRoot(botName: string, chatId: string): string | null {
  const botPath = getBotPath(botName);
  if (!botPath) return null;
  if (!/^[A-Za-z0-9._-]+$/.test(chatId)) return null;
  return path.join(botPath, "sessions", `chat_${chatId}`, "workspace");
}

function validateRelativePath(relativePath: string): void {
  if (relativePath === "") return;
  if (relativePath.includes("\0")) {
    throw new WorkspaceAccessError("NUL byte in path", "invalid_path");
  }
  if (path.isAbsolute(relativePath)) {
    throw new WorkspaceAccessError("Absolute path not allowed", "invalid_path");
  }
  const segments = relativePath.split(/[\\/]/);
  for (const segment of segments) {
    if (segment === "" || segment === "." || segment === "..") {
      throw new WorkspaceAccessError(
        "Path traversal not allowed",
        "invalid_path",
      );
    }
  }
}

function resolveWithinRoot(root: string, relativePath: string): string {
  const joined = path.resolve(root, relativePath);
  const realJoined = fs.existsSync(joined) ? fs.realpathSync(joined) : joined;
  const realRoot = fs.existsSync(root) ? fs.realpathSync(root) : root;
  if (realJoined !== realRoot && !realJoined.startsWith(realRoot + path.sep)) {
    throw new WorkspaceAccessError(
      "Path escapes workspace root",
      "forbidden",
    );
  }
  return realJoined;
}

function listDirectory(
  absoluteDir: string,
  rootRealPath: string,
): WorkspaceTreeNode[] {
  const entries = fs.readdirSync(absoluteDir, { withFileTypes: true });
  const nodes: WorkspaceTreeNode[] = [];
  for (const entry of entries) {
    const absolute = path.join(absoluteDir, entry.name);
    let stat: fs.Stats;
    try {
      stat = fs.statSync(absolute);
    } catch {
      continue;
    }
    const relative = path.relative(rootRealPath, absolute);
    const isDir = entry.isDirectory();
    const node: WorkspaceTreeNode = {
      name: entry.name,
      path: relative,
      type: isDir ? "dir" : "file",
      mtime: stat.mtime.toISOString(),
    };
    if (!isDir) {
      node.size = stat.size;
    }
    nodes.push(node);
  }
  nodes.sort((a, b) => {
    if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  return nodes;
}

/**
 * Lazy directory listing for a bot session's workspace.
 *
 * Walks depth-1 only; nested directories return `children: undefined` so the
 * caller can fetch them on expand. Throws `WorkspaceAccessError` for path
 * traversal, symlink escape, or unknown bot.
 */
export function listBotWorkspaceTree(
  botName: string,
  chatId: string,
  relativePath: string = "",
): WorkspaceTreeResult {
  const root = workspaceRoot(botName, chatId);
  if (!root) {
    throw new WorkspaceAccessError("Unknown bot or session", "not_found");
  }
  validateRelativePath(relativePath);

  if (!fs.existsSync(root)) {
    return { root, relativePath, tree: [], missing: true };
  }
  const realRoot = fs.realpathSync(root);
  const target = resolveWithinRoot(realRoot, relativePath);
  if (!fs.existsSync(target)) {
    throw new WorkspaceAccessError("Path not found", "not_found");
  }
  const stat = fs.statSync(target);
  if (!stat.isDirectory()) {
    throw new WorkspaceAccessError("Path is not a directory", "invalid_path");
  }
  const tree = listDirectory(target, realRoot);
  return { root: realRoot, relativePath, tree, missing: false };
}
