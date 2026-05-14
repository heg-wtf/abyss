import { checkHealth, listChatBots } from "@/lib/abyss-api";
import { MobileSessionsScreen } from "@/components/mobile/mobile-sessions-screen";

export const dynamic = "force-dynamic";

/**
 * Mobile sessions list page (Phase 2 skeleton).
 *
 * Phase 3 will replace the placeholder with bot avatars, last-message
 * previews, and custom rename support. For now the screen only proves
 * the routing + layout integration: the API is queried server-side and
 * the result handed to a thin client shell.
 */
export default async function MobileSessionsPage() {
  const apiOnline = await checkHealth();
  const bots = apiOnline ? await listChatBots().catch(() => []) : [];

  return <MobileSessionsScreen apiOnline={apiOnline} bots={bots} />;
}
