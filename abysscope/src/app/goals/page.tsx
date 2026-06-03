import { GoalsClient } from "@/components/goals/goals-client";

export const dynamic = "force-dynamic";

export default function GoalsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Goals</h1>
        <p className="text-muted-foreground text-sm">
          Per-bot goal tracker (<code className="font-mono text-xs">goals.yaml</code>).
          Bots log progress through the{" "}
          <code className="font-mono text-xs">record_progress</code> MCP tool;
          weekly digest cron summarises the past 7 days. The top 3 active
          goals are injected into the bot&apos;s CLAUDE.md so it can keep
          them in mind without hunting through the file.
        </p>
      </div>
      <GoalsClient />
    </div>
  );
}
