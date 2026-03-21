"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface SessionInfo {
  chatId: string;
  lastActivity: string | null;
  conversationFiles: string[];
  hasSessionId: boolean;
}

interface SessionListProps {
  botName: string;
  initialSessions: SessionInfo[];
}

export function SessionList({ botName, initialSessions }: SessionListProps) {
  const [sessions, setSessions] = useState(initialSessions);

  const handleDelete = async (chatId: string) => {
    if (!window.confirm(`Delete session chat_${chatId}?`)) return;
    await fetch(`/api/bots/${botName}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chatId }),
    });
    setSessions(sessions.filter((s) => s.chatId !== chatId));
  };

  if (sessions.length === 0) {
    return <p className="text-sm text-muted-foreground">No active sessions</p>;
  }

  return (
    <div className="space-y-3">
      {sessions.map((session) => (
        <Card key={session.chatId}>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <Link href={`/bots/${botName}/conversations/${session.chatId}`}>
                <CardTitle className="text-sm font-mono hover:underline cursor-pointer">
                  chat_{session.chatId}
                </CardTitle>
              </Link>
              <div className="flex items-center gap-2">
                {session.hasSessionId && (
                  <Badge variant="outline" className="text-xs">
                    Active
                  </Badge>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleDelete(session.chatId)}
                  className="text-destructive text-xs"
                >
                  Delete
                </Button>
              </div>
            </div>
            {session.lastActivity && (
              <CardDescription className="text-xs">
                Last activity:{" "}
                {new Date(session.lastActivity).toLocaleDateString()}{" "}
                {new Date(session.lastActivity).toLocaleTimeString()}
              </CardDescription>
            )}
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-1">
              {session.conversationFiles.map((file) => (
                <Badge
                  key={file}
                  variant="secondary"
                  className="text-xs font-mono"
                >
                  {file.replace("conversation-", "").replace(".md", "")}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
