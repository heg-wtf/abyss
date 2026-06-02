import { EpisodesClient } from "@/components/episodes/episodes-client";

export const dynamic = "force-dynamic";

export default function EpisodesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Episodes</h1>
        <p className="text-muted-foreground text-sm">
          Per-bot timeline (<code className="font-mono text-xs">episodes.jsonl</code>)
          of facts, events, decisions, and changes pulled out of yesterday&apos;s
          conversation by the nightly extraction cron.
        </p>
      </div>
      <EpisodesClient />
    </div>
  );
}
