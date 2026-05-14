"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
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
  const searchParams = useSearchParams();
  const name = params.name as string;
  const chatId = params.chatId as string;
  const requestedDate = searchParams.get("date") ?? "";

  const [conversationFiles, setConversationFiles] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [content, setContent] = useState<string>("");
  // ``displayName`` is the user-facing bot label (``display_name`` from
  // bot.yaml). Falls back to the URL slug so the breadcrumb never
  // renders empty while the fetch is in flight.
  const [displayName, setDisplayName] = useState<string>(name);

  useEffect(() => {
    fetch(`/api/bots/${name}`)
      .then((r) => r.json())
      .then((data) => {
        if (typeof data?.display_name === "string" && data.display_name.trim()) {
          setDisplayName(data.display_name);
        }
        const session = (data.sessions || []).find(
          (s: SessionData) => s.chatId === chatId,
        );
        if (session) {
          const files = session.conversationFiles as string[];
          setConversationFiles(files);
          if (files.length > 0) {
            const dates = files.map((f) =>
              f.replace("conversation-", "").replace(".md", ""),
            );
            const fallback = dates[dates.length - 1];
            const initial =
              requestedDate && dates.includes(requestedDate)
                ? requestedDate
                : fallback;
            setSelectedDate(initial);
          }
        }
      });
  }, [name, chatId, requestedDate]);

  useEffect(() => {
    if (!selectedDate) return;
    let cancelled = false;
    const controller = new AbortController();
    fetch(`/api/bots/${name}/conversations/${chatId}/${selectedDate}`, {
      signal: controller.signal,
    })
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled) setContent(data.content || "");
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [name, chatId, selectedDate]);

  const handleDeleteConversation = async (date: string) => {
    if (!window.confirm(`Delete conversation-${date}.md?`)) return;
    await fetch(`/api/bots/${name}/conversations/${chatId}/${date}`, {
      method: "DELETE",
    });
    const updated = conversationFiles.filter(
      (f) => f !== `conversation-${date}.md`,
    );
    setConversationFiles(updated);
    if (date === selectedDate) {
      if (updated.length > 0) {
        const latest = updated[updated.length - 1];
        setSelectedDate(latest.replace("conversation-", "").replace(".md", ""));
      } else {
        setSelectedDate("");
        setContent("");
      }
    }
  };

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
          {displayName}
        </Link>
        <span className="text-muted-foreground">/</span>
        <h1 className="text-lg font-bold">chat_{chatId}</h1>
      </div>

      <div className="flex gap-2 flex-wrap items-center">
        {conversationFiles.map((file: string) => {
          const date = file.replace("conversation-", "").replace(".md", "");
          return (
            <div key={date} className="flex items-center gap-0.5">
              <Badge
                variant={date === selectedDate ? "default" : "outline"}
                className="cursor-pointer"
                onClick={() => setSelectedDate(date)}
              >
                {date}
              </Badge>
              <button
                onClick={() => handleDeleteConversation(date)}
                className="text-muted-foreground hover:text-destructive text-xs px-1"
                title={`Delete conversation-${date}.md`}
              >
                x
              </button>
            </div>
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
          {content ? (
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
