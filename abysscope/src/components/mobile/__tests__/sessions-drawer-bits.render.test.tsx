// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render, fireEvent, screen } from "@testing-library/react";
import {
  DrawerFooter,
  RoutineKindIcon,
  TabButton,
} from "../sessions-drawer-bits";

describe("TabButton", () => {
  it("reflects active state via aria-pressed and class hint", () => {
    const { container } = render(
      <TabButton active onClick={() => {}}>
        Chats
      </TabButton>,
    );
    const btn = container.querySelector("button")!;
    expect(btn.getAttribute("aria-pressed")).toBe("true");
    expect(btn.className).toContain("border-b-2");
  });

  it("uses the muted style when inactive", () => {
    const { container } = render(
      <TabButton active={false} onClick={() => {}}>
        Routines
      </TabButton>,
    );
    const btn = container.querySelector("button")!;
    expect(btn.getAttribute("aria-pressed")).toBe("false");
    expect(btn.className).toContain("text-muted-foreground");
  });

  it("invokes onClick when pressed", () => {
    const onClick = vi.fn();
    render(
      <TabButton active={false} onClick={onClick}>
        Routines
      </TabButton>,
    );
    fireEvent.click(screen.getByText("Routines"));
    expect(onClick).toHaveBeenCalled();
  });
});

describe("RoutineKindIcon", () => {
  it("renders the Clock icon for cron kinds", () => {
    const { container } = render(<RoutineKindIcon kind="cron" />);
    expect(container.querySelector(".lucide-clock")).not.toBeNull();
  });

  it("renders the HeartPulse icon for heartbeat kinds", () => {
    const { container } = render(<RoutineKindIcon kind="heartbeat" />);
    expect(container.querySelector(".lucide-heart-pulse")).not.toBeNull();
  });
});

describe("DrawerFooter", () => {
  it("shows the build-time version and links to /settings", () => {
    process.env.NEXT_PUBLIC_ABYSS_VERSION = "2026.05.16";
    delete process.env.NEXT_PUBLIC_ABYSS_COMMIT;
    render(<DrawerFooter />);
    expect(screen.getByText("2026.05.16")).toBeTruthy();
    const settings = screen.getByRole("link", { name: /settings/i });
    expect(settings.getAttribute("href")).toBe("/settings");
  });

  it("falls back to 'dev' when the version env var is missing", () => {
    delete process.env.NEXT_PUBLIC_ABYSS_VERSION;
    render(<DrawerFooter />);
    expect(screen.getByText("dev")).toBeTruthy();
  });

  it("appends the commit short SHA when provided", () => {
    process.env.NEXT_PUBLIC_ABYSS_VERSION = "2026.05.16";
    process.env.NEXT_PUBLIC_ABYSS_COMMIT = "abc1234";
    render(<DrawerFooter />);
    expect(screen.getByText(/abc1234/)).toBeTruthy();
  });
});
