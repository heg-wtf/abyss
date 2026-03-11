"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";

interface StatusData {
  running: boolean;
  pid: number | null;
}

export function LiveStatus({ initialRunning }: { initialRunning: boolean }) {
  const [running, setRunning] = useState(initialRunning);

  useEffect(() => {
    const interval = setInterval(() => {
      fetch("/api/status")
        .then((r) => r.json())
        .then((data: StatusData) => setRunning(data.running))
        .catch(() => {});
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <Badge variant={running ? "default" : "secondary"}>
      <span
        className={`mr-1 inline-block h-2 w-2 rounded-full ${running ? "bg-green-400 animate-pulse" : "bg-gray-400"}`}
      />
      {running ? "Running" : "Stopped"}
    </Badge>
  );
}
