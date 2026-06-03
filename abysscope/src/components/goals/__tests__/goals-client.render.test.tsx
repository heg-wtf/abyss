// @vitest-environment happy-dom
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

vi.mock("@/lib/abyss-api", () => ({
  listChatBots: vi.fn(),
  fetchGoals: vi.fn(),
  addGoal: vi.fn(),
  updateGoal: vi.fn(),
  deleteGoal: vi.fn(),
  recordGoalProgress: vi.fn(),
}));

import { GoalsClient } from "../goals-client";
import * as api from "@/lib/abyss-api";

const goal = {
  id: "ship-blog",
  title: "Ship blog launcher",
  kpi: "PR merged",
  target: "2026-06-15",
  status: "active" as const,
  created_at: "2026-06-03T00:00:00Z",
  progress: [
    { ts: "2026-06-03T01:00:00Z", note: "drafted plan" },
  ],
};

describe("GoalsClient", () => {
  beforeEach(() => {
    vi.mocked(api.listChatBots).mockResolvedValue([
      { name: "anne", display_name: "Anne", type: "claude_code", alias: null },
    ]);
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state when no goals", async () => {
    vi.mocked(api.fetchGoals).mockResolvedValue({ bot: "anne", goals: [] });
    render(<GoalsClient />);
    await waitFor(() => {
      expect(screen.getByText(/No goals/i)).toBeTruthy();
    });
  });

  it("renders goal card with title and timeline", async () => {
    vi.mocked(api.fetchGoals).mockResolvedValue({ bot: "anne", goals: [goal] });
    render(<GoalsClient />);
    await waitFor(() => {
      expect(screen.getByText("Ship blog launcher")).toBeTruthy();
      expect(screen.getByText(/drafted plan/)).toBeTruthy();
    });
  });

  it("calls recordGoalProgress on Log progress click", async () => {
    vi.mocked(api.fetchGoals).mockResolvedValue({ bot: "anne", goals: [goal] });
    vi.mocked(api.recordGoalProgress).mockResolvedValue({
      ok: true,
      entry: { ts: "2026-06-03T02:00:00Z", note: "addressed review" },
    });

    render(<GoalsClient />);
    const input = (await screen.findByLabelText(
      /Progress note for ship-blog/i,
    )) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "addressed review" } });
    fireEvent.click(screen.getByRole("button", { name: /Log progress/i }));
    await waitFor(() => {
      expect(api.recordGoalProgress).toHaveBeenCalledWith(
        "anne",
        "ship-blog",
        "addressed review",
      );
    });
  });

  it("calls updateGoal when Done is clicked", async () => {
    vi.mocked(api.fetchGoals).mockResolvedValue({ bot: "anne", goals: [goal] });
    vi.mocked(api.updateGoal).mockResolvedValue({
      ok: true,
      goal: { ...goal, status: "done" },
    });
    render(<GoalsClient />);
    const button = await screen.findByRole("button", { name: /^Done$/i });
    fireEvent.click(button);
    await waitFor(() => {
      expect(api.updateGoal).toHaveBeenCalledWith("anne", "ship-blog", {
        status: "done",
      });
    });
  });

  it("submits add-goal form", async () => {
    vi.mocked(api.fetchGoals).mockResolvedValue({ bot: "anne", goals: [] });
    vi.mocked(api.addGoal).mockResolvedValue({ ok: true, goal });
    render(<GoalsClient />);
    const title = (await screen.findByLabelText("Title")) as HTMLInputElement;
    fireEvent.change(title, { target: { value: "Ship blog launcher" } });
    fireEvent.click(screen.getByRole("button", { name: /Add goal/i }));
    await waitFor(() => {
      expect(api.addGoal).toHaveBeenCalledWith("anne", {
        title: "Ship blog launcher",
        kpi: undefined,
        target: undefined,
      });
    });
  });

  it("confirms before deleting and skips when user cancels", async () => {
    vi.mocked(api.fetchGoals).mockResolvedValue({ bot: "anne", goals: [goal] });
    Object.defineProperty(window, "confirm", {
      value: () => false,
      configurable: true,
    });
    render(<GoalsClient />);
    const button = await screen.findByRole("button", { name: /Delete/i });
    fireEvent.click(button);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(api.deleteGoal).not.toHaveBeenCalled();
  });
});
