// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MessageBubble } from "../mobile-chat-message-bubble";
import type { ConversationMessage } from "../mobile-chat-types";

function makeMessage(
  overrides: Partial<ConversationMessage> = {},
): ConversationMessage {
  return {
    id: "m1",
    role: "assistant",
    content: "hello",
    timestamp: new Date("2026-05-16T10:00:00").toISOString(),
    ...overrides,
  } as ConversationMessage;
}

describe("MessageBubble", () => {
  it("renders user content as plain pre-wrap text (no markdown)", () => {
    render(
      <MessageBubble
        message={makeMessage({ role: "user", content: "**bold not parsed**" })}
      />,
    );
    expect(screen.getByText("**bold not parsed**")).toBeTruthy();
  });

  it("renders assistant content through MarkdownBody (bold tag emitted)", () => {
    const { container } = render(
      <MessageBubble message={makeMessage({ content: "**bold parsed**" })} />,
    );
    expect(container.querySelector("strong")).not.toBeNull();
  });

  it("aligns user bubbles to the right and assistant bubbles to the left", () => {
    const { container, rerender } = render(
      <MessageBubble message={makeMessage({ role: "user" })} />,
    );
    expect(container.querySelector("li.justify-end")).not.toBeNull();

    rerender(<MessageBubble message={makeMessage({ role: "assistant" })} />);
    expect(container.querySelector("li.justify-start")).not.toBeNull();
  });

  it("renders an attachment chip for each attachment", () => {
    render(
      <MessageBubble
        message={makeMessage({
          attachments: [
            {
              display_name: "design.png",
              real_name: "abc__design.png",
              mime: "image/png",
              size: 12345,
              url: "/files/abc__design.png",
            },
            {
              display_name: "notes.pdf",
              real_name: "def__notes.pdf",
              mime: "application/pdf",
              size: 7890,
              url: "/files/def__notes.pdf",
            },
          ],
        })}
      />,
    );
    expect(screen.getByText(/design\.png/)).toBeTruthy();
    expect(screen.getByText(/notes\.pdf/)).toBeTruthy();
  });

  it("renders a download chip when commandFile is present", () => {
    render(
      <MessageBubble
        message={makeMessage({
          commandFile: {
            name: "report.csv",
            path: "uploads/report.csv",
            url: "/files/report.csv",
          },
        })}
      />,
    );
    const link = screen.getByText(/report\.csv/).closest("a");
    expect(link).not.toBeNull();
    expect(link!.getAttribute("href")).toBe("/files/report.csv");
    expect(link!.getAttribute("download")).toBe("report.csv");
  });

  it("shows the queued indicator and wires the cancel callback", () => {
    const onCancelQueue = vi.fn();
    render(
      <MessageBubble
        message={makeMessage({ role: "user" })}
        queued
        onCancelQueue={onCancelQueue}
      />,
    );
    expect(screen.getByText(/응답 완료 후 전송/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText(/cancel queued message/i));
    expect(onCancelQueue).toHaveBeenCalled();
  });

  it("renders the formatted message time in ko-KR 24h", () => {
    const { container } = render(
      <MessageBubble
        message={makeMessage({
          timestamp: new Date("2026-05-16T15:07:00").toISOString(),
        })}
      />,
    );
    expect(container.textContent).toContain("15:07");
  });
});
