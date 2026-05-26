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

export interface WorkspaceFileResult {
  root: string;
  relativePath: string;
  content: string;
  size: number;
  mtime: string;
  truncated: boolean;
}

/**
 * Hard cap on inline preview size. Markdown plans / logs are usually
 * tens of KB; anything past this is almost certainly a runaway log
 * we do not want to ship over the wire for an inline preview. The
 * reader returns the first ``MAX_PREVIEW_BYTES`` bytes and sets
 * ``truncated: true`` so the UI can flag it.
 */
export const MAX_PREVIEW_BYTES = 1024 * 1024;

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
  // ``ChatSession.id`` from the Python sidecar is the full directory
  // name (e.g. ``chat_web_<uuid>``) but legacy callers pass the bare
  // chatId without the ``chat_`` prefix. Normalize both forms.
  const normalized = chatId.startsWith("chat_") ? chatId.slice(5) : chatId;
  if (!/^[A-Za-z0-9._-]+$/.test(normalized)) return null;
  return path.join(botPath, "sessions", `chat_${normalized}`, "workspace");
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

/**
 * Read a single text file from a bot session's workspace.
 *
 * Reuses the same root resolution + symlink-escape guard as the tree
 * listing. Caps the read at `MAX_PREVIEW_BYTES` so a runaway log can
 * never blow up the preview surface. Throws `WorkspaceAccessError`
 * for unknown bot, traversal, escape, or directory targets.
 */
export function readBotWorkspaceFile(
  botName: string,
  chatId: string,
  relativePath: string,
): WorkspaceFileResult {
  const root = workspaceRoot(botName, chatId);
  if (!root) {
    throw new WorkspaceAccessError("Unknown bot or session", "not_found");
  }
  if (!relativePath) {
    throw new WorkspaceAccessError("Path is required", "invalid_path");
  }
  validateRelativePath(relativePath);

  if (!fs.existsSync(root)) {
    throw new WorkspaceAccessError("Workspace not found", "not_found");
  }
  const realRoot = fs.realpathSync(root);
  const target = resolveWithinRoot(realRoot, relativePath);
  if (!fs.existsSync(target)) {
    throw new WorkspaceAccessError("Path not found", "not_found");
  }
  const stat = fs.statSync(target);
  if (stat.isDirectory()) {
    throw new WorkspaceAccessError("Path is a directory", "invalid_path");
  }
  if (!stat.isFile()) {
    throw new WorkspaceAccessError("Path is not a regular file", "invalid_path");
  }

  // Read up to MAX_PREVIEW_BYTES via a file descriptor so an oversized
  // file does not allocate the whole blob in memory. ``readSync``
  // returns the number of bytes actually written into the buffer.
  const truncated = stat.size > MAX_PREVIEW_BYTES;
  const readLength = Math.min(stat.size, MAX_PREVIEW_BYTES);
  const buffer = Buffer.alloc(readLength);
  if (readLength > 0) {
    const fd = fs.openSync(target, "r");
    try {
      let offset = 0;
      while (offset < readLength) {
        const bytesRead = fs.readSync(
          fd,
          buffer,
          offset,
          readLength - offset,
          offset,
        );
        if (bytesRead === 0) break;
        offset += bytesRead;
      }
    } finally {
      fs.closeSync(fd);
    }
  }
  const content = buffer.toString("utf-8");

  return {
    root: realRoot,
    relativePath: path.relative(realRoot, target),
    content,
    size: stat.size,
    mtime: stat.mtime.toISOString(),
    truncated,
  };
}
