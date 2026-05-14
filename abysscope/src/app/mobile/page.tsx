import { MobileSessionsScreen } from "@/components/mobile/mobile-sessions-screen";
import { checkHealth, listChatBots } from "@/lib/abyss-api";

export const dynamic = "force-dynamic";

/**
 * Mobile entry — chat list.
 *
 * ``/mobile`` *is* the sessions list. The earlier revision used a
 * server redirect to ``/mobile/sessions`` to leave room for a
 * different future landing screen (e.g. "open the last chat I was
 * in"), but the indirection is just a wasted hop today and made the
 * URL longer than it needs to be on a phone.
 */
export default async function MobileIndexPage() {
  const apiOnline = await checkHealth();
  const bots = apiOnline ? await listChatBots().catch(() => []) : [];
  return <MobileSessionsScreen apiOnline={apiOnline} bots={bots} />;
}
