"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

interface DaemonLogInfo {
  name: string;
  size: number;
  exists: boolean;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getLogDate(filename: string): Date | null {
  const match = filename.match(/^cclaw-(\d{2})(\d{2})(\d{2})\.log$/);
  if (!match) return null;
  return new Date(
    2000 + parseInt(match[1]),
    parseInt(match[2]) - 1,
    parseInt(match[3]),
  );
}

export default function LogsPage() {
  const [files, setFiles] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>("");
  const [lines, setLines] = useState<string[]>([]);
  const [totalLines, setTotalLines] = useState(0);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [daemonLogs, setDaemonLogs] = useState<DaemonLogInfo[]>([]);

  const fetchFiles = () => {
    fetch("/api/logs")
      .then((r) => r.json())
      .then((data) => {
        setFiles(data.files || []);
        setDaemonLogs(data.daemonLogs || []);
        if (data.files?.length > 0 && !data.files.includes(selectedFile)) {
          setSelectedFile(data.files[0]);
        }
      });
  };

  useEffect(() => {
    fetch("/api/logs")
      .then((r) => r.json())
      .then((data) => {
        setFiles(data.files || []);
        setDaemonLogs(data.daemonLogs || []);
        if (data.files?.length > 0) {
          setSelectedFile(data.files[0]);
        }
      });
  }, []);

  useEffect(() => {
    if (!selectedFile) return;
    let cancelled = false;
    const controller = new AbortController();
    const loadContent = async () => {
      setLoading(true);
      try {
        const r = await fetch(`/api/logs?file=${selectedFile}&limit=1000`, {
          signal: controller.signal,
        });
        const data = await r.json();
        if (!cancelled) {
          setLines(data.lines || []);
          setTotalLines(data.totalLines || 0);
          setLoading(false);
        }
      } catch {
        /* aborted */
      }
    };
    loadContent();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [selectedFile]);

  const filteredLines = filter
    ? lines.filter((line) => line.toLowerCase().includes(filter.toLowerCase()))
    : lines;

  const deleteFiles = async (filesToDelete: string[]) => {
    await fetch("/api/logs", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files: filesToDelete }),
    });
    if (filesToDelete.includes(selectedFile)) {
      setSelectedFile("");
      setLines([]);
      setTotalLines(0);
    }
    fetchFiles();
  };

  const handleDeleteCurrent = () => {
    if (!selectedFile) return;
    if (!window.confirm(`Delete ${selectedFile}?`)) return;
    deleteFiles([selectedFile]);
  };

  const handleDeleteOlderThan = (days: number) => {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);
    const oldFiles = files.filter((f) => {
      const date = getLogDate(f);
      return date && date < cutoff;
    });
    if (oldFiles.length === 0) {
      window.alert(`No log files older than ${days} days.`);
      return;
    }
    if (
      !window.confirm(
        `Delete ${oldFiles.length} log files older than ${days} days?`,
      )
    )
      return;
    deleteFiles(oldFiles);
  };

  const handleDeleteAll = () => {
    if (files.length === 0) return;
    if (!window.confirm(`Delete all ${files.length} log files?`)) return;
    deleteFiles([...files]);
  };

  const handleTruncateDaemon = async () => {
    const totalSize = daemonLogs
      .filter((d) => d.exists)
      .reduce((sum, d) => sum + d.size, 0);
    if (totalSize === 0) return;
    if (!window.confirm(`Truncate daemon logs (${formatSize(totalSize)})?`))
      return;
    await fetch("/api/logs", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "truncate-daemon" }),
    });
    fetchFiles();
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Logs</h1>
        <p className="text-muted-foreground text-sm">
          Daily rotating log files
        </p>
      </div>

      <div className="flex items-center gap-4">
        <Select
          value={selectedFile}
          onValueChange={(value) => {
            if (value) setSelectedFile(value);
          }}
        >
          <SelectTrigger className="w-[220px]">
            <SelectValue placeholder="Select log file" />
          </SelectTrigger>
          <SelectContent>
            {files.map((file) => (
              <SelectItem key={file} value={file}>
                {file}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Input
          placeholder="Filter logs..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="max-w-xs"
        />

        <span className="text-xs text-muted-foreground">
          {filteredLines.length}
          {filter ? ` / ${lines.length}` : ""} lines (total: {totalLines})
        </span>

        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleDeleteCurrent}
            disabled={!selectedFile}
            className="text-destructive"
          >
            Delete
          </Button>
          <Select
            onValueChange={(value) => {
              if (value === "7") handleDeleteOlderThan(7);
              else if (value === "30") handleDeleteOlderThan(30);
              else if (value === "all") handleDeleteAll();
            }}
          >
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="Delete old..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Older than 7d</SelectItem>
              <SelectItem value="30">Older than 30d</SelectItem>
              <SelectItem value="all">All logs</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-mono">{selectedFile}</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : (
            <ScrollArea className="h-[600px]">
              <pre className="text-xs font-mono whitespace-pre-wrap">
                {filteredLines.join("\n")}
              </pre>
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      {daemonLogs.some((d) => d.exists) && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">Daemon Logs</CardTitle>
              <Button
                variant="outline"
                size="sm"
                onClick={handleTruncateDaemon}
                className="text-destructive"
              >
                Truncate
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-1 text-sm">
              {daemonLogs.map((log) =>
                log.exists ? (
                  <div
                    key={log.name}
                    className="flex justify-between font-mono text-xs"
                  >
                    <span>{log.name}</span>
                    <span className="text-muted-foreground">
                      {formatSize(log.size)}
                    </span>
                  </div>
                ) : null,
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
