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

export default function LogsPage() {
  const [files, setFiles] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>("");
  const [lines, setLines] = useState<string[]>([]);
  const [totalLines, setTotalLines] = useState(0);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/logs")
      .then((r) => r.json())
      .then((data) => {
        setFiles(data.files || []);
        if (data.files?.length > 0) {
          setSelectedFile(data.files[0]);
        }
      });
  }, []);

  useEffect(() => {
    if (!selectedFile) return;
    setLoading(true);
    fetch(`/api/logs?file=${selectedFile}&limit=1000`)
      .then((r) => r.json())
      .then((data) => {
        setLines(data.lines || []);
        setTotalLines(data.totalLines || 0);
      })
      .finally(() => setLoading(false));
  }, [selectedFile]);

  const filteredLines = filter
    ? lines.filter((line) => line.toLowerCase().includes(filter.toLowerCase()))
    : lines;

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
    </div>
  );
}
