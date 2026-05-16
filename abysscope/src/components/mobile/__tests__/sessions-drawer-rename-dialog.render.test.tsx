// @vitest-environment happy-dom
import { describe, expect, it, vi, afterEach, beforeEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { RenameSessionDialog } from "../sessions-drawer-rename-dialog";
import type { ChatSession } from "@/lib/abyss-api";

function makeSession(overrides: Partial<ChatSession> = {}): ChatSession {
  return {
    id: "chat-abc",
    bot: "testbot",
    bot_display_name: "Test Bot",
    custom_name: "old name",
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

describe("RenameSessionDialog", () => {
  it("renders nothing when session is null", () => {
    const { container } = render(
      <RenameSessionDialog
        session={null}
        onClose={() => {}}
        onRenamed={() => {}}
      />,
    );
    expect(container.querySelector('[role="dialog"]')).toBeNull();
  });

  it("seeds the input with the session's current custom name", () => {
    render(
      <RenameSessionDialog
        session={makeSession({ custom_name: "morning chat" })}
        onClose={() => {}}
        onRenamed={() => {}}
      />,
    );
    expect(
      (screen.getByPlaceholderText(/economy questions/) as HTMLInputElement)
        .value,
    ).toBe("morning chat");
  });

  it("posts to the rename endpoint with the URL-encoded ids", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ custom_name: "new label" }),
    });
    const onRenamed = vi.fn();
    const onClose = vi.fn();
    render(
      <RenameSessionDialog
        session={makeSession({ id: "chat with space", bot: "testbot" })}
        onClose={onClose}
        onRenamed={onRenamed}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText(/economy questions/), {
      target: { value: "new label" },
    });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      "/api/chat/sessions/testbot/chat%20with%20space/rename",
    );
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ name: "new label" });

    await waitFor(() =>
      expect(onRenamed).toHaveBeenCalledWith({
        bot: "testbot",
        id: "chat with space",
        custom_name: "new label",
      }),
    );
    expect(onClose).toHaveBeenCalled();
  });

  it("does not call onRenamed when the server replies !ok", async () => {
    fetchMock.mockResolvedValue({ ok: false });
    const onRenamed = vi.fn();
    const onClose = vi.fn();
    render(
      <RenameSessionDialog
        session={makeSession()}
        onClose={onClose}
        onRenamed={onRenamed}
      />,
    );
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(onRenamed).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("calls onClose when Cancel is pressed", () => {
    const onClose = vi.fn();
    render(
      <RenameSessionDialog
        session={makeSession()}
        onClose={onClose}
        onRenamed={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("Cancel"));
    expect(onClose).toHaveBeenCalled();
  });
});
