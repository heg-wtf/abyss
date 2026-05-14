import { redirect } from "next/navigation";
import { MobileBootstrapScreen } from "@/components/mobile/mobile-bootstrap-screen";
import {
  checkHealth,
  listChatBots,
  listChatSessions,
} from "@/lib/abyss-api";

export const dynamic = "force-dynamic";

/**
 * Mobile entry.
 *
 * Earlier this rendered a full-screen sessions list that competed
 * with the in-chat slide drawer. The user asked to remove that
 * surface — everything happens inside the chat now, with the drawer
 * as the only session switcher.
 *
 * So ``/mobile`` resolves to the most recently updated chat and
 * server-redirects there. When there are no chats yet (fresh install,
 * cleared sessions), we render a tiny bootstrap screen that lets the
 * user create the first one — there's no chat to land in yet, and
 * showing the chat screen with an empty session id would 404.
 */
export default async function MobileIndexPage() {
  const apiOnline = await checkHealth();
  if (!apiOnline) {
    return <MobileBootstrapScreen apiOnline={false} bots={[]} />;
  }

  const bots = await listChatBots().catch(() => []);
  if (bots.length === 0) {
    return <MobileBootstrapScreen apiOnline bots={[]} />;
  }

  // Fan out across every bot in parallel — sessions are scoped per
  // bot, so picking "the most recent chat" needs the whole set.
  const perBot = await Promise.all(
    bots.map((bot) => listChatSessions(bot.name).catch(() => [])),
  );
  const sessions = perBot.flat();
  if (sessions.length === 0) {
    return <MobileBootstrapScreen apiOnline bots={bots} />;
  }

  const latest = sessions.reduce((newest, current) =>
    current.updated_at.localeCompare(newest.updated_at) > 0
      ? current
      : newest,
  );
  redirect(`/mobile/chat/${latest.bot}/${latest.id}`);
}
