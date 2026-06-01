import { SelfClient } from "@/components/self/self-client";

export const dynamic = "force-dynamic";

export default function SelfPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Self Reflection</h1>
        <p className="text-muted-foreground text-sm">
          Each bot keeps a single <code className="font-mono text-xs">SELF.md</code>{" "}
          with its own mistake patterns, sticky topics, irritation triggers, and
          self-correction rules. A weekly reflection cron updates it from the
          recent conversation log and feedback signals; manual edits land here.
        </p>
      </div>
      <SelfClient />
    </div>
  );
}
