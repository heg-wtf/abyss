import { ChatView } from "@/components/chat/chat-view";
import { checkHealth, listChatBots } from "@/lib/abyss-api";

export const dynamic = "force-dynamic";

export default async function ChatPage() {
  const apiOnline = await checkHealth();
  const bots = apiOnline ? await listChatBots().catch(() => []) : [];
  return (
    <div className="h-[calc(100vh-3rem)]">
      <ChatView initialBots={bots} apiOnline={apiOnline} />
    </div>
  );
}
