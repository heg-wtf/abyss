// @vitest-environment happy-dom
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

vi.mock("@/lib/abyss-api", () => ({
  listChatBots: vi.fn(),
  fetchSkillProposals: vi.fn(),
  approveSkillProposal: vi.fn(),
  rejectSkillProposal: vi.fn(),
}));

import { ProposalsClient } from "../proposals-client";
import * as api from "@/lib/abyss-api";

const proposal = {
  id: "p1",
  bot: "anne",
  candidate_url: "https://github.com/owner/cool-skill",
  reasons: ["needed stripe fetcher"],
  alternative_urls: [],
  proposed_at: "2026-06-03T00:00:00Z",
  resolved_at: null,
  status: "pending" as const,
};

describe("ProposalsClient", () => {
  beforeEach(() => {
    vi.mocked(api.listChatBots).mockResolvedValue([
      { name: "anne", display_name: "Anne", type: "claude_code", alias: null },
    ]);
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state when no proposals exist", async () => {
    vi.mocked(api.fetchSkillProposals).mockResolvedValue({
      bot: "anne",
      proposals: [],
    });
    render(<ProposalsClient />);
    await waitFor(() => {
      expect(screen.getByText(/No proposals/i)).toBeTruthy();
    });
  });

  it("renders proposal row with approve + reject buttons", async () => {
    vi.mocked(api.fetchSkillProposals).mockResolvedValue({
      bot: "anne",
      proposals: [proposal],
    });
    render(<ProposalsClient />);
    await waitFor(() => {
      expect(screen.getByText(/github.com\/owner\/cool-skill/)).toBeTruthy();
      expect(screen.getByRole("button", { name: /Approve/i })).toBeTruthy();
      expect(screen.getByRole("button", { name: /Reject/i })).toBeTruthy();
    });
  });

  it("calls approve API and reloads on click", async () => {
    vi.mocked(api.fetchSkillProposals).mockResolvedValue({
      bot: "anne",
      proposals: [proposal],
    });
    vi.mocked(api.approveSkillProposal).mockResolvedValue({
      ok: true,
      skill_name: "cool-skill",
    });

    render(<ProposalsClient />);
    const button = await screen.findByRole("button", { name: /Approve/i });
    fireEvent.click(button);
    await waitFor(() => {
      expect(api.approveSkillProposal).toHaveBeenCalledWith("anne", "p1");
    });
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toMatch(/cool-skill/);
    });
  });

  it("surfaces approve failure with stage and error", async () => {
    vi.mocked(api.fetchSkillProposals).mockResolvedValue({
      bot: "anne",
      proposals: [proposal],
    });
    vi.mocked(api.approveSkillProposal).mockResolvedValue({
      ok: false,
      stage: "import",
      error: "git clone failed",
    });

    render(<ProposalsClient />);
    const button = await screen.findByRole("button", { name: /Approve/i });
    fireEvent.click(button);
    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert.textContent).toMatch(/import/);
      expect(alert.textContent).toMatch(/git clone failed/);
    });
  });

  it("reject calls API only when the confirm dialog is accepted", async () => {
    vi.mocked(api.fetchSkillProposals).mockResolvedValue({
      bot: "anne",
      proposals: [proposal],
    });
    vi.mocked(api.rejectSkillProposal).mockResolvedValue({
      ok: true,
      proposal: { ...proposal, status: "rejected" },
    });
    Object.defineProperty(window, "confirm", {
      value: () => true,
      configurable: true,
    });

    render(<ProposalsClient />);
    const button = await screen.findByRole("button", { name: /Reject/i });
    fireEvent.click(button);
    await waitFor(() => {
      expect(api.rejectSkillProposal).toHaveBeenCalledWith("anne", "p1");
    });
  });
});
