import { PersonaClient } from "@/components/persona/persona-client";

export const dynamic = "force-dynamic";

export default function PersonaPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Persona Drift</h1>
        <p className="text-muted-foreground text-sm">
          Daily snapshots of the bot&apos;s composed{" "}
          <code className="font-mono text-xs">CLAUDE.md</code> let abyss spot
          when the bot&apos;s effective personality starts shifting — usually
          when compact, SELF.md rewrites, or new goals accumulate. The drift
          report compares the latest snapshot against the closest one in the
          chosen window. Compact-induced shrinkage past 10% also fires a Web
          Push automatically.
        </p>
      </div>
      <PersonaClient />
    </div>
  );
}
