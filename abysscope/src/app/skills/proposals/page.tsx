import { ProposalsClient } from "@/components/skills/proposals-client";

export const dynamic = "force-dynamic";

export default function SkillProposalsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Skill Proposals</h1>
        <p className="text-muted-foreground text-sm">
          Bots flag missing capabilities via the{" "}
          <code className="font-mono text-xs">propose_skill</code> MCP tool.
          Approve to clone the GitHub repo, install it as a skill, and attach
          it to the bot. Reject to tell the bot the URL is not wanted (it
          will not be re-proposed).
        </p>
      </div>
      <ProposalsClient />
    </div>
  );
}
