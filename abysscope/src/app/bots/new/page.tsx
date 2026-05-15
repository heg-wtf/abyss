import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { NewBotForm } from "@/components/bots/new-bot-form";

/**
 * New bot creation surface.
 *
 * Mirrors the CLI ``abyss bot add`` flow but in a web form so the
 * user doesn't have to drop into a terminal just to add a bot.
 * Submission goes through ``POST /api/bots/new`` → chat_server
 * ``POST /chat/bots`` → ``onboarding.create_bot`` on disk, so the
 * resulting ``bot.yaml`` is byte-identical to a CLI-created bot.
 */
export const dynamic = "force-dynamic";

export default function NewBotPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 pb-12">
      <div className="space-y-1">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" aria-hidden />
          Back to dashboard
        </Link>
        <h1 className="text-2xl font-semibold">New bot</h1>
        <p className="text-sm text-muted-foreground">
          Same fields as <code className="font-mono text-xs">abyss bot add</code>.
          The bot is chattable immediately; cron and heartbeat schedulers
          attach on the next daemon restart.
        </p>
      </div>

      <NewBotForm />
    </div>
  );
}
