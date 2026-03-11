"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

interface SessionData {
  chatId: string;
  conversationFiles: string[];
}

export default function ConversationPage() {
  const params = useParams();
  const name = params.name as string;
  const chatId = params.chatId as string;

  const [sessions, setSessions] = useState<SessionData[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [content, setContent] = useState<string>("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch(`/api/bots/${name}`)
      .then((r) => r.json())
      .then((data) => {
        const session = (data.sessions || []).find(
          (s: SessionData) => s.chatId === chatId,
        );
        if (session) {
          setSessions([session]);
          const files = session.conversationFiles as string[];
          if (files.length > 0) {
            const latest = files[files.length - 1];
            const date = latest.replace("conversation-", "").replace(".md", "");
            setSelectedDate(date);
          }
        }
      });
  }, [name, chatId]);

  useEffect(() => {
    if (!selectedDate) return;
    setLoading(true);
    fetch(`/api/bots/${name}/conversations/${chatId}/${selectedDate}`)
      .then((r) => r.json())
      .then((data) => setContent(data.content || ""))
      .finally(() => setLoading(false));
  }, [name, chatId, selectedDate]);

  const conversationFiles =
    sessions.length > 0 ? sessions[0].conversationFiles : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link
          href="/"
          className="text-muted-foreground hover:text-foreground text-sm"
        >
          Dashboard
        </Link>
        <span className="text-muted-foreground">/</span>
        <Link
          href={`/bots/${name}`}
          className="text-muted-foreground hover:text-foreground text-sm"
        >
          {name}
        </Link>
        <span className="text-muted-foreground">/</span>
        <h1 className="text-lg font-bold">chat_{chatId}</h1>
      </div>

      <div className="flex gap-2 flex-wrap">
        {conversationFiles.map((file: string) => {
          const date = file.replace("conversation-", "").replace(".md", "");
          return (
            <Badge
              key={date}
              variant={date === selectedDate ? "default" : "outline"}
              className="cursor-pointer"
              onClick={() => setSelectedDate(date)}
            >
              {date}
            </Badge>
          );
        })}
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-mono">
            conversation-{selectedDate}.md
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : content ? (
            <ScrollArea className="h-[600px]">
              <pre className="text-sm whitespace-pre-wrap">{content}</pre>
            </ScrollArea>
          ) : (
            <p className="text-sm text-muted-foreground">No content</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
