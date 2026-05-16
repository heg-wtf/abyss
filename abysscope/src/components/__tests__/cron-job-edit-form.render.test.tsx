// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { JobEditForm } from "../cron-job-edit-form";
import type { CronJob } from "@/lib/abyss";

function recurring(overrides: Partial<CronJob> = {}): CronJob {
  return {
    name: "morning",
    enabled: true,
    schedule: "0 9 * * *",
    message: "Run morning sync",
    ...overrides,
  };
}

function oneShot(overrides: Partial<CronJob> = {}): CronJob {
  return {
    name: "remind",
    enabled: true,
    at: "2026-12-31T09:00:00",
    message: "Remind me",
    ...overrides,
  };
}

describe("JobEditForm", () => {
  it("renders Schedule input for recurring jobs and At input for one-shot", () => {
    const { rerender } = render(
      <JobEditForm
        job={recurring()}
        index={0}
        availableSkills={[]}
        onUpdate={() => {}}
        onDone={() => {}}
        onRemove={() => {}}
      />,
    );
    expect(screen.getByDisplayValue("0 9 * * *")).toBeTruthy();
    expect(screen.queryByText(/At \(ISO datetime/)).toBeNull();

    rerender(
      <JobEditForm
        job={oneShot()}
        index={0}
        availableSkills={[]}
        onUpdate={() => {}}
        onDone={() => {}}
        onRemove={() => {}}
      />,
    );
    expect(screen.getByDisplayValue("2026-12-31T09:00:00")).toBeTruthy();
    expect(screen.getByText(/Delete after run/)).toBeTruthy();
  });

  it("emits onUpdate when the message textarea changes", () => {
    const onUpdate = vi.fn();
    render(
      <JobEditForm
        job={recurring()}
        index={2}
        availableSkills={[]}
        onUpdate={onUpdate}
        onDone={() => {}}
        onRemove={() => {}}
      />,
    );
    fireEvent.change(screen.getByDisplayValue("Run morning sync"), {
      target: { value: "Updated message" },
    });
    expect(onUpdate).toHaveBeenCalledWith(2, { message: "Updated message" });
  });

  it("toggles a skill in/out of the job's skills array", () => {
    const onUpdate = vi.fn();
    render(
      <JobEditForm
        job={recurring({ skills: [] })}
        index={1}
        availableSkills={["qmd", "translate"]}
        onUpdate={onUpdate}
        onDone={() => {}}
        onRemove={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("qmd"));
    expect(onUpdate).toHaveBeenCalledWith(1, { skills: ["qmd"] });
  });

  it("flips the job between recurring and one-shot via the Type buttons", () => {
    const onUpdate = vi.fn();
    render(
      <JobEditForm
        job={recurring()}
        index={0}
        availableSkills={[]}
        onUpdate={onUpdate}
        onDone={() => {}}
        onRemove={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("One-shot"));
    expect(onUpdate).toHaveBeenCalledWith(0, {
      ...recurring(),
      schedule: undefined,
      at: "",
    });
  });

  it("invokes onDone and onRemove from the header buttons", () => {
    const onDone = vi.fn();
    const onRemove = vi.fn();
    render(
      <JobEditForm
        job={recurring()}
        index={3}
        availableSkills={[]}
        onUpdate={() => {}}
        onDone={onDone}
        onRemove={onRemove}
      />,
    );
    fireEvent.click(screen.getByText("Done"));
    expect(onDone).toHaveBeenCalled();
    fireEvent.click(screen.getByText("Remove"));
    expect(onRemove).toHaveBeenCalledWith(3);
  });
});
