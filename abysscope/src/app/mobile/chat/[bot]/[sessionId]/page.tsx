import { notFound } from "next/navigation";
import {
  getChatMessages,
  listChatBots,
  listChatSessions,
} from "@/lib/abyss-api";
import { MobileChatScreen } from "@/components/mobile/mobile-chat-screen";

export const dynamic = "force-dynamic";

/**
 * Mobile chat screen for a specific bot + session pair.
 *
 * The page is intentionally thin: it resolves the bot + session pair
 * server-side so the client never renders a flash of "loading" before
 * confirming the session exists. The actual UI lives in
 * ``MobileChatScreen`` so unit tests can drive it without Next.js.
 */
export default async function MobileChatPage({
  params,
}: {
  params: Promise<{ bot: string; sessionId: string }>;
}) {
  const { bot, sessionId } = await params;

  const [bots, sessions] = await Promise.all([
    listChatBots().catch(() => []),
    listChatSessions(bot).catch(() => []),
  ]);

  const session = sessions.find((s) => s.id === sessionId);
  if (!session) {
    notFound();
  }

  const initialMessages = await getChatMessages(bot, sessionId).catch(() => []);

  return (
    <MobileChatScreen
      bots={bots}
      session={session}
      initialMessages={initialMessages}
    />
  );
}
