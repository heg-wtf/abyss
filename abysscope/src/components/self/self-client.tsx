"use client";

import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  fetchSelfMd,
  listChatBots,
  saveSelfMd,
  type BotSummary,
} from "@/lib/abyss-api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

type Mode = "view" | "edit";

export function SelfClient() {
  const [bots, setBots] = React.useState<BotSummary[]>([]);
  const [activeBot, setActiveBot] = React.useState<string | null>(null);
  const [content, setContent] = React.useState<string>("");
  const [draft, setDraft] = React.useState<string>("");
  const [mode, setMode] = React.useState<Mode>("view");
  const [loading, setLoading] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    listChatBots()
      .then((list) => {
        if (cancelled) return;
        setBots(list);
        if (list.length > 0) {
          setActiveBot((current) => current ?? list[0].name);
        }
      })
      .catch((caught: unknown) =>
        setError(caught instanceof Error ? caught.message : "failed to load bots"),
      );
    return () => {
      cancelled = true;
    };
  }, []);

  const loadSelf = React.useCallback(
    async (bot: string) => {
      setLoading(true);
      setError(null);
      try {
        const resp = await fetchSelfMd(bot);
        setContent(resp.content);
        setDraft(resp.content);
        setMode("view");
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "failed to load SELF.md");
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  React.useEffect(() => {
    if (activeBot) {
      void loadSelf(activeBot);
    }
  }, [activeBot, loadSelf]);

  const handleSave = async () => {
    if (!activeBot) return;
    setSaving(true);
    setError(null);
    try {
      await saveSelfMd(activeBot, draft);
      setContent(draft);
      setMode("view");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "failed to save SELF.md");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setDraft(content);
    setMode("view");
  };

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-destructive text-sm">
          {error}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {bots.map((bot) => (
          <Button
            key={bot.name}
            variant={bot.name === activeBot ? "default" : "outline"}
            size="sm"
            onClick={() => setActiveBot(bot.name)}
          >
            {bot.display_name || bot.name}
          </Button>
        ))}
      </div>

      {activeBot && (
        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-2">
            <div>
              <CardTitle>SELF.md — {activeBot}</CardTitle>
              <CardDescription>
                The bot&apos;s self-reflection notebook. Updated by the weekly
                reflection cron or{" "}
                <code className="font-mono text-xs">abyss self reflect</code>.
              </CardDescription>
            </div>
            <div className="flex gap-2">
              {mode === "view" ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setMode("edit")}
                  disabled={loading}
                >
                  Edit
                </Button>
              ) : (
                <>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={handleCancel}
                    disabled={saving}
                  >
                    Cancel
                  </Button>
                  <Button size="sm" onClick={handleSave} disabled={saving}>
                    {saving ? "Saving…" : "Save"}
                  </Button>
                </>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-muted-foreground text-sm">Loading…</p>
            ) : mode === "view" ? (
              content.trim() ? (
                <div className="prose dark:prose-invert max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
                </div>
              ) : (
                <p className="text-muted-foreground text-sm">
                  SELF.md is empty. Run{" "}
                  <code className="font-mono text-xs">
                    abyss self reflect {activeBot}
                  </code>{" "}
                  to populate it.
                </p>
              )
            ) : (
              <Textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                className="min-h-[360px] font-mono text-sm"
                spellCheck={false}
              />
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
