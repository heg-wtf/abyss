import { FactsClient } from "@/components/facts/facts-client";

export const dynamic = "force-dynamic";

export default function FactsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Facts</h1>
        <p className="text-muted-foreground text-sm">
          Per-bot structured store (<code className="font-mono text-xs">facts.db</code>)
          of subject / claim / confidence triples extracted nightly from the
          conversation log. Retract bad rows here; the bot stops recalling them.
        </p>
      </div>
      <FactsClient />
    </div>
  );
}
