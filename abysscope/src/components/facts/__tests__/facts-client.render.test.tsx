// @vitest-environment happy-dom
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

vi.mock("@/lib/abyss-api", () => ({
  listChatBots: vi.fn(),
  fetchFacts: vi.fn(),
  retractFact: vi.fn(),
}));

import { FactsClient } from "../facts-client";
import * as api from "@/lib/abyss-api";

const sampleFact = {
  id: 7,
  subject: "release",
  claim: "v2026.06.02 shipped",
  confidence: 0.9,
  source_turn: "conversation-260601.md",
  source_episode_id: null,
  status: "active" as const,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

describe("FactsClient", () => {
  beforeEach(() => {
    vi.mocked(api.listChatBots).mockResolvedValue([
      { name: "anne", display_name: "Anne", type: "claude_code", alias: null },
    ]);
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state with extract hint", async () => {
    vi.mocked(api.fetchFacts).mockResolvedValue({ bot: "anne", facts: [] });
    render(<FactsClient />);
    await waitFor(() => {
      expect(screen.getByText(/No facts yet/i)).toBeTruthy();
    });
  });

  it("renders facts table for active rows", async () => {
    vi.mocked(api.fetchFacts).mockResolvedValue({
      bot: "anne",
      facts: [sampleFact],
    });
    render(<FactsClient />);
    await waitFor(() => {
      expect(screen.getByText("v2026.06.02 shipped")).toBeTruthy();
      expect(screen.getByRole("button", { name: /Retract/i })).toBeTruthy();
    });
  });

  it("calls retract API and refreshes table", async () => {
    vi.mocked(api.fetchFacts).mockResolvedValue({
      bot: "anne",
      facts: [sampleFact],
    });
    vi.mocked(api.retractFact).mockResolvedValue(undefined);
    Object.defineProperty(window, "confirm", { value: () => true, configurable: true });

    render(<FactsClient />);
    const button = await screen.findByRole("button", { name: /Retract/i });
    fireEvent.click(button);
    await waitFor(() => {
      expect(api.retractFact).toHaveBeenCalledWith("anne", 7);
    });
  });

  it("respects user cancelling the confirm dialog", async () => {
    vi.mocked(api.fetchFacts).mockResolvedValue({
      bot: "anne",
      facts: [sampleFact],
    });
    Object.defineProperty(window, "confirm", { value: () => false, configurable: true });

    render(<FactsClient />);
    const button = await screen.findByRole("button", { name: /Retract/i });
    fireEvent.click(button);
    // Allow any pending promises to flush.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(api.retractFact).not.toHaveBeenCalled();
  });
});
