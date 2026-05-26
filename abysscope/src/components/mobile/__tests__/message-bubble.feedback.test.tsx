// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MessageBubble } from "../mobile-chat-message-bubble";
import type { ConversationMessage } from "../mobile-chat-types";

// ``FeedbackButtons`` hits the Next.js proxy directly via ``fetch`` so
// the request lands on the same origin the PWA was served from (the
// phone cannot reach the Python sidecar on 127.0.0.1 over Tailscale).
// Tests stub ``window.fetch`` to mirror that contract.
const fetchMock = vi.fn();

function makeAssistantMessage(
  overrides: Partial<ConversationMessage> = {},
): ConversationMessage {
  return {
    id: "m1",
    role: "assistant",
    content: "hello",
    timestamp: "2026-05-19 08:00:00 UTC",
    ...overrides,
  } as ConversationMessage;
}

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(
    new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  window.localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("MessageBubble feedback footer", () => {
  it("does not render feedback buttons without bot+sessionId", () => {
    render(<MessageBubble message={makeAssistantMessage()} />);
    expect(screen.queryByLabelText(/피드백 1/)).toBeNull();
    expect(screen.queryByLabelText(/피드백 2/)).toBeNull();
    expect(screen.queryByLabelText(/피드백 3/)).toBeNull();
  });

  it("does not render feedback buttons for user messages", () => {
    render(
      <MessageBubble
        message={makeAssistantMessage({ role: "user", content: "hi" })}
        bot="anne"
        sessionId="chat_web_abc"
      />,
    );
    expect(screen.queryByLabelText(/피드백 1/)).toBeNull();
  });

  it("does not render feedback buttons while streaming", () => {
    render(
      <MessageBubble
        message={makeAssistantMessage({ streaming: true })}
        bot="anne"
        sessionId="chat_web_abc"
      />,
    );
    expect(screen.queryByLabelText(/피드백 1/)).toBeNull();
  });

  it("renders 1/2/3 buttons under assistant message and posts on click", async () => {
    render(
      <MessageBubble
        message={makeAssistantMessage()}
        bot="anne"
        sessionId="chat_web_abc"
      />,
    );

    const one = screen.getByLabelText(/피드백 1/);
    const two = screen.getByLabelText(/피드백 2/);
    const three = screen.getByLabelText(/피드백 3/);
    expect(one).toBeTruthy();
    expect(two).toBeTruthy();
    expect(three).toBeTruthy();

    fireEvent.click(two);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/chat/sessions/anne/chat_web_abc/feedback",
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            turn_id: "2026-05-19 08:00:00 UTC",
            signal: 2,
          }),
        }),
      );
    });

    // selected button reflects aria-pressed
    await waitFor(() => {
      expect(two.getAttribute("aria-pressed")).toBe("true");
    });
  });

  it("persists selection to localStorage and restores it on remount", async () => {
    const { unmount } = render(
      <MessageBubble
        message={makeAssistantMessage()}
        bot="anne"
        sessionId="chat_web_abc"
      />,
    );

    fireEvent.click(screen.getByLabelText(/피드백 1/));

    await waitFor(() => {
      expect(window.localStorage.getItem(
        "feedback:anne:chat_web_abc:2026-05-19 08:00:00 UTC",
      )).toBe("1");
    });

    unmount();

    render(
      <MessageBubble
        message={makeAssistantMessage()}
        bot="anne"
        sessionId="chat_web_abc"
      />,
    );
    await waitFor(() => {
      expect(
        screen.getByLabelText(/피드백 1/).getAttribute("aria-pressed"),
      ).toBe("true");
    });
  });

  it("shows error label when post fails", async () => {
    fetchMock.mockRejectedValueOnce(new Error("network"));
    render(
      <MessageBubble
        message={makeAssistantMessage()}
        bot="anne"
        sessionId="chat_web_abc"
      />,
    );

    fireEvent.click(screen.getByLabelText(/피드백 3/));

    await waitFor(() => {
      expect(screen.getByText(/저장 실패/)).toBeTruthy();
    });
  });
});
