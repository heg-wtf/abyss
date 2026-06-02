// @vitest-environment happy-dom
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/abyss-api", () => ({
  listChatBots: vi.fn(),
  fetchEpisodes: vi.fn(),
}));

import { EpisodesClient } from "../episodes-client";
import * as api from "@/lib/abyss-api";

describe("EpisodesClient", () => {
  beforeEach(() => {
    vi.mocked(api.listChatBots).mockResolvedValue([
      { name: "anne", display_name: "Anne", type: "claude_code", alias: null },
    ]);
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state when no episodes exist", async () => {
    vi.mocked(api.fetchEpisodes).mockResolvedValue({ bot: "anne", episodes: [] });
    render(<EpisodesClient />);
    await waitFor(() => {
      expect(screen.getByText(/No episodes yet/i)).toBeTruthy();
    });
  });

  it("renders episodes grouped by date newest-first", async () => {
    vi.mocked(api.fetchEpisodes).mockResolvedValue({
      bot: "anne",
      episodes: [
        {
          ts: "2026-06-01T10:00:00Z",
          date: "2026-06-01",
          kind: "decision",
          summary: "ship phase 4",
          source_turn: "conversation-260601.md#t1",
          meta: {},
        },
        {
          ts: "2026-05-30T10:00:00Z",
          date: "2026-05-30",
          kind: "fact",
          summary: "release dropped",
          source_turn: "",
          meta: {},
        },
      ],
    });
    render(<EpisodesClient />);
    await waitFor(() => {
      expect(screen.getByText(/ship phase 4/)).toBeTruthy();
      expect(screen.getByText(/release dropped/)).toBeTruthy();
    });
    // Date headers visible.
    expect(screen.getByText("2026-06-01")).toBeTruthy();
    expect(screen.getByText("2026-05-30")).toBeTruthy();
  });

  it("propagates fetch errors to the user", async () => {
    vi.mocked(api.fetchEpisodes).mockRejectedValue(new Error("boom"));
    render(<EpisodesClient />);
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/boom/);
    });
  });
});
