import { AboutMeClient } from "@/components/about-me/about-me-client";

export const dynamic = "force-dynamic";

export default function AboutMePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">About Me</h1>
        <p className="text-muted-foreground text-sm">
          Shared user knowledge base across all bots. When a bot learns a new
          fact, it&apos;s added as a{" "}
          <span className="font-medium">propose</span> — approve or reject with
          one tap.
        </p>
      </div>
      <AboutMeClient />
    </div>
  );
}
