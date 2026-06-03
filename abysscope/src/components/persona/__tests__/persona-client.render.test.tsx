// @vitest-environment happy-dom
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

vi.mock("@/lib/abyss-api", () => ({
  listChatBots: vi.fn(),
  fetchPersonaSnapshots: vi.fn(),
  fetchPersonaDrift: vi.fn(),
  triggerPersonaSnapshot: vi.fn(),
}));

import { PersonaClient } from "../persona-client";
import * as api from "@/lib/abyss-api";

const snapshot = {
  ts: "2026-06-03T00:00:00+00:00",
  hash: "abcdef0123456789",
  total_bytes: 1234,
  section_sizes: { A: 600, B: 634 },
  event: "daily" as const,
};

describe("PersonaClient", () => {
  beforeEach(() => {
    vi.mocked(api.listChatBots).mockResolvedValue([
      { name: "anne", display_name: "Anne", type: "claude_code", alias: null },
    ]);
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state with snapshot CTA", async () => {
    vi.mocked(api.fetchPersonaSnapshots).mockResolvedValue({
      bot: "anne",
      snapshots: [],
    });
    vi.mocked(api.fetchPersonaDrift).mockResolvedValue({
      bot: "anne",
      drift: null,
    });
    render(<PersonaClient />);
    await waitFor(() => {
      expect(screen.getByText(/No snapshots yet/i)).toBeTruthy();
    });
    expect(
      screen.getByText(/Not enough snapshot history yet/i),
    ).toBeTruthy();
  });

  it("renders snapshot table when data is available", async () => {
    vi.mocked(api.fetchPersonaSnapshots).mockResolvedValue({
      bot: "anne",
      snapshots: [snapshot],
    });
    vi.mocked(api.fetchPersonaDrift).mockResolvedValue({
      bot: "anne",
      drift: null,
    });
    render(<PersonaClient />);
    await waitFor(() => {
      expect(screen.getByText(/2026-06-03T00:00:00\+00:00/)).toBeTruthy();
      expect(screen.getByText(/1,234/)).toBeTruthy();
    });
  });

  it("renders drift report with shrinkage badge", async () => {
    vi.mocked(api.fetchPersonaSnapshots).mockResolvedValue({
      bot: "anne",
      snapshots: [snapshot],
    });
    vi.mocked(api.fetchPersonaDrift).mockResolvedValue({
      bot: "anne",
      drift: {
        latest_ts: "2026-06-03T00:00:00+00:00",
        baseline_ts: "2026-05-27T00:00:00+00:00",
        latest_bytes: 500,
        baseline_bytes: 1500,
        total_delta_bytes: -1000,
        total_delta_pct: -0.6667,
        hash_changed: true,
        section_deltas: { A: -800, B: -200 },
        shrinkage_alert: true,
      },
    });
    render(<PersonaClient />);
    await waitFor(() => {
      expect(screen.getByText(/Shrinkage alert/i)).toBeTruthy();
    });
    expect(screen.getByText(/-1,000/)).toBeTruthy();
  });

  it("triggers snapshot API on button click", async () => {
    vi.mocked(api.fetchPersonaSnapshots).mockResolvedValue({
      bot: "anne",
      snapshots: [],
    });
    vi.mocked(api.fetchPersonaDrift).mockResolvedValue({
      bot: "anne",
      drift: null,
    });
    vi.mocked(api.triggerPersonaSnapshot).mockResolvedValue({
      ok: true,
      snapshot,
    });
    render(<PersonaClient />);
    const button = await screen.findByRole("button", { name: /Take snapshot/i });
    fireEvent.click(button);
    await waitFor(() => {
      expect(api.triggerPersonaSnapshot).toHaveBeenCalledWith("anne");
    });
  });

  it("surfaces fetch errors", async () => {
    vi.mocked(api.fetchPersonaSnapshots).mockRejectedValue(new Error("boom"));
    vi.mocked(api.fetchPersonaDrift).mockResolvedValue({
      bot: "anne",
      drift: null,
    });
    render(<PersonaClient />);
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/boom/);
    });
  });
});
