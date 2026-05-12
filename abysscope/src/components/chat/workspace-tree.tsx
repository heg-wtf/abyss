"use client";

import * as React from "react";
import {
  ChevronDown,
  ChevronRight,
  ExternalLink,
  File as FileIcon,
  Folder,
  FolderOpen,
  RefreshCw,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

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
              onClick={() => toggleDirectory(node)}
              className={cn(
                "flex w-full items-center gap-1 rounded px-1 py-0.5 text-left text-xs hover:bg-muted",
                node.type === "file" && "cursor-default hover:bg-transparent",
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

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex h-14 items-center justify-between border-b px-3">
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
      </div>
      {error && (
        <div className="border-b bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}
      <ScrollArea className="min-h-0 flex-1">
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
      </ScrollArea>
    </div>
  );
}
