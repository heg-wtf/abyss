// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { JobViewCard } from "../cron-job-view-card";
import type { CronJob } from "@/lib/abyss";

function recurring(overrides: Partial<CronJob> = {}): CronJob {
  return {
    name: "morning",
    enabled: true,
    schedule: "0 9 * * *",
    message: "Run morning sync",
    timezone: "Asia/Seoul",
    ...overrides,
  };
}

function oneShot(overrides: Partial<CronJob> = {}): CronJob {
  return {
    name: "remind",
    enabled: true,
    at: "2026-12-31T09:00:00",
    message: "Remind me",
    delete_after_run: true,
    ...overrides,
  };
}

describe("JobViewCard", () => {
  it("renders the job name, message, schedule and timezone for recurring jobs", () => {
    render(<JobViewCard job={recurring()} />);
    expect(screen.getByText("morning")).toBeTruthy();
    expect(screen.getByText("Run morning sync")).toBeTruthy();
    expect(screen.getByText(/0 9 \* \* \*/)).toBeTruthy();
    expect(screen.getByText(/Asia\/Seoul/)).toBeTruthy();
  });

  it("shows Active badge when enabled and Disabled badge otherwise", () => {
    const { rerender } = render(<JobViewCard job={recurring()} />);
    expect(screen.getByText("Active")).toBeTruthy();

    rerender(<JobViewCard job={recurring({ enabled: false })} />);
    expect(screen.getByText("Disabled")).toBeTruthy();
  });

  it("renders 'at: <iso>' instead of the schedule for one-shot jobs", () => {
    render(<JobViewCard job={oneShot()} />);
    expect(screen.getByText(/at: 2026-12-31T09:00:00/)).toBeTruthy();
    expect(screen.getByText("One-shot")).toBeTruthy();
  });

  it("renders model and skill badges when present", () => {
    render(
      <JobViewCard
        job={recurring({ model: "opus", skills: ["qmd", "translate"] })}
      />,
    );
    expect(screen.getByText("opus")).toBeTruthy();
    expect(screen.getByText("qmd")).toBeTruthy();
    expect(screen.getByText("translate")).toBeTruthy();
  });

  it("omits the One-shot badge for recurring jobs", () => {
    render(<JobViewCard job={recurring()} />);
    expect(screen.queryByText("One-shot")).toBeNull();
  });
});
