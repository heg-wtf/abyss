"use client";

import * as React from "react";
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  File as FileIcon,
  Folder,
  FolderOpen,
  RefreshCw,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

/**
 * File extensions we render inline as markdown / plain text. Anything
 * not in this set falls through to "open in Finder" -- we never try
 * to inline a binary in the side panel.
 */
const PREVIEW_EXTENSIONS = new Set([
  ".md",
  ".markdown",
  ".mdx",
  ".txt",
  ".log",
  ".yaml",
  ".yml",
  ".json",
  ".toml",
  ".sh",
  ".py",
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
]);

const MARKDOWN_EXTENSIONS = new Set([".md", ".markdown", ".mdx"]);

function getExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

interface WorkspaceFileResponse {
  root: string;
  relativePath: string;
  content: string;
  size: number;
  mtime: string;
  truncated: boolean;
}

async function fetchFile(
  bot: string,
  sessionId: string,
  relativePath: string,
): Promise<WorkspaceFileResponse> {
  const params = new URLSearchParams({
    bot,
    session: sessionId,
    path: relativePath,
  });
  const response = await fetch(
    `/api/chat/workspace/file?${params.toString()}`,
  );
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${response.status}`);
  }
  return (await response.json()) as WorkspaceFileResponse;
}

interface WorkspaceTreeNode {
  name: string;
  path: string;
  type: "file" | "dir";
  size?: number;
  mtime: string;
  children?: WorkspaceTreeNode[];
}

interface WorkspaceResponse {
  root: string;
  relativePath: string;
  tree: WorkspaceTreeNode[];
  missing: boolean;
}

interface Props {
  bot: string;
  sessionId: string;
  onClose: () => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

async function fetchTree(
  bot: string,
  sessionId: string,
  relativePath: string,
): Promise<WorkspaceResponse> {
  const params = new URLSearchParams({ bot, session: sessionId });
  if (relativePath) params.set("path", relativePath);
  const response = await fetch(`/api/chat/workspace?${params.toString()}`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${response.status}`);
  }
  return (await response.json()) as WorkspaceResponse;
}

export function WorkspaceTree({ bot, sessionId, onClose }: Props) {
  const [root, setRoot] = React.useState<string | null>(null);
  const [missing, setMissing] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [childrenByPath, setChildrenByPath] = React.useState<
    Record<string, WorkspaceTreeNode[]>
  >({});
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set());
  const [loadingPaths, setLoadingPaths] = React.useState<Set<string>>(
    new Set(),
  );
  // Inline preview state. When ``previewPath`` is non-null the panel
  // body switches from the tree to the rendered file. The tree is
  // intentionally kept mounted (no remount on back) so expand state
  // survives the round-trip.
  const [previewPath, setPreviewPath] = React.useState<string | null>(null);
  const [previewName, setPreviewName] = React.useState<string>("");
  const [previewContent, setPreviewContent] = React.useState<string>("");
  const [previewTruncated, setPreviewTruncated] =
    React.useState<boolean>(false);
  const [previewLoading, setPreviewLoading] = React.useState<boolean>(false);
  const [previewError, setPreviewError] = React.useState<string | null>(null);

  const loadRoot = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchTree(bot, sessionId, "");
      setRoot(result.root);
      setMissing(result.missing);
      setChildrenByPath({ "": result.tree });
      setExpanded(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [bot, sessionId]);

  React.useEffect(() => {
    void loadRoot();
  }, [loadRoot]);

  const toggleDirectory = async (node: WorkspaceTreeNode) => {
    if (node.type !== "dir") return;
    const key = node.path;
    if (expanded.has(key)) {
      setExpanded((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
      return;
    }
    if (!childrenByPath[key]) {
      setLoadingPaths((prev) => new Set(prev).add(key));
      try {
        const result = await fetchTree(bot, sessionId, key);
        setChildrenByPath((prev) => ({ ...prev, [key]: result.tree }));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        return;
      } finally {
        setLoadingPaths((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      }
    }
    setExpanded((prev) => new Set(prev).add(key));
  };

  const openPreview = async (node: WorkspaceTreeNode) => {
    const ext = getExtension(node.name);
    if (!PREVIEW_EXTENSIONS.has(ext)) return;
    setPreviewPath(node.path);
    setPreviewName(node.name);
    setPreviewContent("");
    setPreviewTruncated(false);
    setPreviewError(null);
    setPreviewLoading(true);
    try {
      const result = await fetchFile(bot, sessionId, node.path);
      setPreviewContent(result.content);
      setPreviewTruncated(result.truncated);
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : String(err));
    } finally {
      setPreviewLoading(false);
    }
  };

  const closePreview = () => {
    setPreviewPath(null);
    setPreviewName("");
    setPreviewContent("");
    setPreviewError(null);
    setPreviewTruncated(false);
  };

  const reloadPreview = async () => {
    if (!previewPath) return;
    setPreviewError(null);
    setPreviewLoading(true);
    try {
      const result = await fetchFile(bot, sessionId, previewPath);
      setPreviewContent(result.content);
      setPreviewTruncated(result.truncated);
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : String(err));
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleNodeClick = (node: WorkspaceTreeNode) => {
    if (node.type === "file") {
      void openPreview(node);
      return;
    }
    void toggleDirectory(node);
  };

  const openInFinder = async () => {
    if (!root) return;
    await fetch("/api/open-finder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: root }),
    }).catch(() => undefined);
  };

  const renderNodes = (nodes: WorkspaceTreeNode[], depth: number) => (
    <ul className="space-y-px">
      {nodes.map((node) => {
        const isOpen = expanded.has(node.path);
        const childRows = childrenByPath[node.path];
        const isLoading = loadingPaths.has(node.path);
        return (
          <li key={node.path}>
            <button
              type="button"
              onClick={() => handleNodeClick(node)}
              className={cn(
                "flex w-full items-center gap-1 rounded px-1 py-0.5 text-left text-xs hover:bg-muted",
                node.type === "file" &&
                  !PREVIEW_EXTENSIONS.has(getExtension(node.name)) &&
                  "cursor-default hover:bg-transparent",
              )}
              style={{ paddingLeft: `${depth * 12 + 4}px` }}
              title={node.path}
            >
              {node.type === "dir" ? (
                <>
                  {isOpen ? (
                    <ChevronDown className="size-3 shrink-0" />
                  ) : (
                    <ChevronRight className="size-3 shrink-0" />
                  )}
                  {isOpen ? (
                    <FolderOpen className="size-3.5 shrink-0 text-amber-500" />
                  ) : (
                    <Folder className="size-3.5 shrink-0 text-amber-500" />
                  )}
                </>
              ) : (
                <>
                  <span className="size-3 shrink-0" />
                  <FileIcon className="size-3.5 shrink-0 text-muted-foreground" />
                </>
              )}
              <span className="truncate flex-1">{node.name}</span>
              {node.type === "file" && typeof node.size === "number" && (
                <span className="ml-2 shrink-0 text-[10px] text-muted-foreground">
                  {formatBytes(node.size)}
                </span>
              )}
              {isLoading && (
                <RefreshCw className="size-3 shrink-0 animate-spin text-muted-foreground" />
              )}
            </button>
            {isOpen && childRows && childRows.length > 0 && (
              <div>{renderNodes(childRows, depth + 1)}</div>
            )}
            {isOpen && childRows && childRows.length === 0 && (
              <div
                className="px-1 py-0.5 text-[11px] text-muted-foreground"
                style={{ paddingLeft: `${(depth + 1) * 12 + 4}px` }}
              >
                (empty)
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );

  const rootNodes = childrenByPath[""] ?? [];
  const inPreview = previewPath !== null;
  const previewExt = previewName ? getExtension(previewName) : "";
  const renderAsMarkdown = MARKDOWN_EXTENSIONS.has(previewExt);

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex h-14 items-center justify-between border-b px-3">
        {inPreview ? (
          <>
            <div className="flex min-w-0 items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                onClick={closePreview}
                aria-label="목록으로 돌아가기"
                title="목록으로 돌아가기"
              >
                <ArrowLeft className="size-4" />
              </Button>
              <span
                className="truncate text-sm font-medium"
                title={previewPath ?? undefined}
              >
                {previewName}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => void reloadPreview()}
                disabled={previewLoading}
                aria-label="새로고침"
                title="새로고침"
              >
                <RefreshCw
                  className={cn(
                    "size-4",
                    previewLoading && "animate-spin",
                  )}
                />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={onClose}
                aria-label="작업 디렉토리 패널 닫기"
                title="닫기"
              >
                <X className="size-4" />
              </Button>
            </div>
          </>
        ) : (
          <>
            <span className="text-sm font-medium">Workspace</span>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => void openInFinder()}
                disabled={!root}
                aria-label="Finder에서 열기"
                title="Finder에서 열기"
              >
                <ExternalLink className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => void loadRoot()}
                disabled={loading}
                aria-label="새로고침"
                title="새로고침"
              >
                <RefreshCw
                  className={cn("size-4", loading && "animate-spin")}
                />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={onClose}
                aria-label="작업 디렉토리 패널 닫기"
                title="닫기"
              >
                <X className="size-4" />
              </Button>
            </div>
          </>
        )}
      </div>
      {!inPreview && error && (
        <div className="border-b bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}
      {inPreview && previewError && (
        <div className="border-b bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {previewError}
        </div>
      )}
      {inPreview && previewTruncated && (
        <div className="border-b bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
          파일이 너무 큽니다. 앞부분만 표시합니다.
        </div>
      )}
      <ScrollArea className="min-h-0 flex-1">
        {inPreview ? (
          <div className="p-3">
            {previewLoading && (
              <div className="px-1 py-2 text-xs text-muted-foreground">
                Loading…
              </div>
            )}
            {!previewLoading && !previewError && renderAsMarkdown && (
              <div className="prose prose-sm dark:prose-invert max-w-none break-words [overflow-wrap:anywhere] prose-pre:my-2 prose-pre:max-w-full prose-pre:overflow-x-auto prose-pre:rounded-md prose-pre:bg-background/40 prose-pre:p-2 prose-img:max-w-full">
                <ReactMarkdown
                  remarkPlugins={[remarkBreaks, remarkGfm]}
                  rehypePlugins={[rehypeHighlight]}
                >
                  {previewContent || ""}
                </ReactMarkdown>
              </div>
            )}
            {!previewLoading && !previewError && !renderAsMarkdown && (
              <pre className="overflow-x-auto rounded-md bg-muted/50 p-2 text-[11px] leading-relaxed">
                <code>{previewContent}</code>
              </pre>
            )}
          </div>
        ) : (
          <div className="p-2">
            {loading && rootNodes.length === 0 && (
              <div className="px-1 py-2 text-xs text-muted-foreground">
                Loading…
              </div>
            )}
            {!loading && missing && (
              <div className="px-1 py-2 text-xs text-muted-foreground">
                workspace 디렉토리가 아직 없습니다. 봇이 파일을 만들면 여기에
                표시됩니다.
              </div>
            )}
            {!loading && !missing && rootNodes.length === 0 && !error && (
              <div className="px-1 py-2 text-xs text-muted-foreground">
                (empty)
              </div>
            )}
            {rootNodes.length > 0 && renderNodes(rootNodes, 0)}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
