/**
 * Source-level regression guards.
 *
 * Several UI fixes have been silently dropped during squash merges (the
 * `bot_display_name` rendering and the sidebar collapse toggle were both
 * lost twice). These checks read the relevant source files and assert that
 * the load-bearing snippets are still in place. They run in the existing
 * Vitest (node env) suite without any extra DOM dependency.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

function read(relPath: string): string {
  return readFileSync(path.join(ROOT, relPath), "utf8");
}

describe("UI regression guards", () => {
  it("BotSelector trigger renders display_name, not the slug", () => {
    const source = read("chat/bot-selector.tsx");
    // The shadcn SelectValue placeholder is the failure mode — it
    // shows whatever the option's `value` prop is (the slug). The fix
    // explicitly looks up the BotSummary and renders display_name.
    // Strip comment lines so a description that mentions the JSX tag
    // doesn't trip the regex.
    const code = source
      .split("\n")
      .filter((line) => !line.trim().startsWith("//"))
      .join("\n");
    expect(code).not.toMatch(/<SelectValue\b/);
    expect(code).toMatch(/selected\?\.display_name|selected\.display_name/);
  });

  it("ChatSessionList shows bot_display_name with avatar fallback", () => {
    const source = read("chat/chat-session-list.tsx");
    expect(source).toMatch(/session\.bot_display_name/);
    expect(source).toMatch(/from "@\/components\/bot-avatar"/);
  });

  it("ChatView routes display_name through delete confirm and prompt", () => {
    const source = read("chat/chat-view.tsx");
    // Delete confirm should not name-drop the slug verbatim.
    expect(source).not.toMatch(/Delete chat with \$\{session\.bot\}/);
    expect(source).toMatch(/session\.bot_display_name/);
    // Streaming prompt placeholder uses the display name.
    expect(source).toMatch(/activeSession\.bot_display_name/);
  });

  it("ChatView isolates stream + messages per session", () => {
    const source = read("chat/chat-view.tsx");
    // Must use the multi-session hook, not the legacy single-stream one.
    expect(source).toMatch(/useMultiSessionChatStream/);
    expect(source).not.toMatch(/\buseChatStream\b/);
    // messages are stored per sessionId in a Map.
    expect(source).toMatch(
      /sessionMessages[\s\S]*Map<string,\s*ConversationMessage\[\]>/
    );
    // PromptInput disabled is keyed on the active session's stream only,
    // never a global flag. The bug was `stream.streaming` blocking all
    // sessions during any one's response.
    expect(source).toMatch(/activeStream\.streaming/);
    expect(source).not.toMatch(/disabled=\{!activeSession \|\| stream\.streaming\}/);
    // Delete must cancel the session's in-flight stream so it does not
    // keep writing into a discarded message Map.
    expect(source).toMatch(/stream\.cancel\(session\.id\)/);
  });

  it("Sidebar exposes a collapse toggle persisted to localStorage", () => {
    const source = read("sidebar.tsx");
    expect(source).toMatch(/abysscope\.sidebar\.collapsed/);
    // Both expand and collapse buttons must be present.
    expect(source).toMatch(/aria-label="Collapse sidebar"/);
    expect(source).toMatch(/aria-label="Expand sidebar"/);
  });

  it("ChatMessage renders the bot's avatar and display name", () => {
    const source = read("chat/chat-message.tsx");
    expect(source).toMatch(/BotAvatar/);
    expect(source).toMatch(/botDisplayName/);
  });
});
