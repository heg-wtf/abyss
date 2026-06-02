// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SelfClient } from "../self-client";
import type { BotSummary } from "@/lib/abyss-api";

const listChatBotsMock = vi.fn();
const fetchSelfMdMock = vi.fn();
const saveSelfMdMock = vi.fn();

vi.mock("@/lib/abyss-api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/abyss-api")>(
    "@/lib/abyss-api",
  );
  return {
    ...actual,
    listChatBots: () => listChatBotsMock(),
    fetchSelfMd: (bot: string) => fetchSelfMdMock(bot),
    saveSelfMd: (bot: string, content: string) => saveSelfMdMock(bot, content),
  };
});

const bots: BotSummary[] = [
  { name: "anne", display_name: "Anne", type: "chat" },
  { name: "ben", display_name: "Ben", type: "chat" },
];

describe("SelfClient", () => {
  beforeEach(() => {
    listChatBotsMock.mockReset();
    fetchSelfMdMock.mockReset();
    saveSelfMdMock.mockReset();
  });

  it("lists bots and renders SELF.md for the first bot", async () => {
    listChatBotsMock.mockResolvedValue(bots);
    fetchSelfMdMock.mockResolvedValue({
      bot: "anne",
      content: "## Mistake patterns\n- talks too much\n",
    });

    render(<SelfClient />);

    await waitFor(() => {
      expect(screen.getByText("Anne")).toBeTruthy();
      expect(screen.getByText("Ben")).toBeTruthy();
    });
    await waitFor(() =>
      expect(screen.getByText(/talks too much/)).toBeTruthy(),
    );
    expect(fetchSelfMdMock).toHaveBeenCalledWith("anne");
  });

  it("shows an empty-state hint when SELF.md is blank", async () => {
    listChatBotsMock.mockResolvedValue(bots);
    fetchSelfMdMock.mockResolvedValue({ bot: "anne", content: "" });

    render(<SelfClient />);

    await waitFor(() =>
      expect(screen.getByText(/SELF\.md is empty/)).toBeTruthy(),
    );
  });

  it("switches active bot and reloads SELF.md", async () => {
    listChatBotsMock.mockResolvedValue(bots);
    fetchSelfMdMock
      .mockResolvedValueOnce({ bot: "anne", content: "anne notes" })
      .mockResolvedValueOnce({ bot: "ben", content: "ben notes" });

    render(<SelfClient />);

    await waitFor(() => expect(screen.getByText(/anne notes/)).toBeTruthy());
    fireEvent.click(screen.getByText("Ben"));
    await waitFor(() => expect(screen.getByText(/ben notes/)).toBeTruthy());
    expect(fetchSelfMdMock).toHaveBeenLastCalledWith("ben");
  });

  it("saves edits via PUT /self", async () => {
    listChatBotsMock.mockResolvedValue(bots);
    fetchSelfMdMock.mockResolvedValue({ bot: "anne", content: "old" });
    saveSelfMdMock.mockResolvedValue(undefined);

    render(<SelfClient />);

    await waitFor(() => expect(screen.getByText(/old/)).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: /edit/i }));
    const textbox = await screen.findByRole("textbox");
    fireEvent.change(textbox, { target: { value: "new notes" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(saveSelfMdMock).toHaveBeenCalledWith("anne", "new notes"),
    );
  });
});
