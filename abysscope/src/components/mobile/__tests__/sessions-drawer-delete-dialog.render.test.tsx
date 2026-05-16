// @vitest-environment happy-dom
import { describe, expect, it, vi, afterEach, beforeEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { DeleteSessionDialog } from "../sessions-drawer-delete-dialog";
import type { ChatSession } from "@/lib/abyss-api";

function makeSession(overrides: Partial<ChatSession> = {}): ChatSession {
  return {
    id: "chat-abc",
    bot: "testbot",
    bot_display_name: "Test Bot",
    custom_name: null,
    created_at: "2026-05-16T00:00:00Z",
    updated_at: "2026-05-16T00:00:00Z",
    ...overrides,
  } as ChatSession;
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("DeleteSessionDialog", () => {
  it("renders nothing when session is null", () => {
    const { container } = render(
      <DeleteSessionDialog
        session={null}
        onClose={() => {}}
        onDeleted={() => {}}
      />,
    );
    expect(container.querySelector('[role="dialog"]')).toBeNull();
  });

  it("issues a DELETE to the URL-encoded session endpoint", async () => {
    fetchMock.mockResolvedValue({ ok: true });
    const onDeleted = vi.fn();
    const onClose = vi.fn();
    render(
      <DeleteSessionDialog
        session={makeSession({ id: "id with space", bot: "test bot" })}
        onClose={onClose}
        onDeleted={onDeleted}
      />,
    );
    fireEvent.click(screen.getByText("Delete"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/chat/sessions/test%20bot/id%20with%20space");
    expect(init.method).toBe("DELETE");

    await waitFor(() =>
      expect(onDeleted).toHaveBeenCalledWith({
        bot: "test bot",
        id: "id with space",
      }),
    );
    expect(onClose).toHaveBeenCalled();
  });

  it("does not call onDeleted when the server replies !ok", async () => {
    fetchMock.mockResolvedValue({ ok: false });
    const onDeleted = vi.fn();
    const onClose = vi.fn();
    render(
      <DeleteSessionDialog
        session={makeSession()}
        onClose={onClose}
        onDeleted={onDeleted}
      />,
    );
    fireEvent.click(screen.getByText("Delete"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(onDeleted).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("invokes onClose when Cancel is pressed", () => {
    const onClose = vi.fn();
    render(
      <DeleteSessionDialog
        session={makeSession()}
        onClose={onClose}
        onDeleted={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("Cancel"));
    expect(onClose).toHaveBeenCalled();
  });
});
