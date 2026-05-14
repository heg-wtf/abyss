import { notFound } from "next/navigation";
import {
  getRoutineMessages,
  listRoutines,
  type RoutineSummary,
} from "@/lib/abyss-api";
import { MobileRoutineScreen } from "@/components/mobile/mobile-routine-screen";

export const dynamic = "force-dynamic";

/**
 * Read-only mobile detail view for a cron job or heartbeat session.
 *
 * Resolves the routine server-side so a stale link 404s instead of
 * flashing an empty surface. Reuses ``MobileChatScreen``'s message
 * styling via ``MobileRoutineScreen`` but drops the input bar +
 * slash sheet — there is nothing to send to a scheduled task.
 */
export default async function MobileRoutinePage({
  params,
}: {
  params: Promise<{ bot: string; kind: string; job: string }>;
}) {
  const { bot, kind, job } = await params;
  if (kind !== "cron" && kind !== "heartbeat") notFound();

  const routines = await listRoutines().catch(() => [] as RoutineSummary[]);
  const routine = routines.find(
    (entry) =>
      entry.bot === bot && entry.kind === kind && entry.job_name === job,
  );
  if (!routine) notFound();

  const messages = await getRoutineMessages(
    bot,
    kind as RoutineSummary["kind"],
    job,
  ).catch(() => []);

  return (
    <MobileRoutineScreen routine={routine} initialMessages={messages} />
  );
}
