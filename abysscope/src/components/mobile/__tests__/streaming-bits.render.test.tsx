// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render, fireEvent, screen } from "@testing-library/react";
import {
  CancelStreamButton,
  StreamingDots,
} from "../mobile-chat-streaming";

describe("StreamingDots", () => {
  it("renders three dot spans by default (block layout)", () => {
    const { container } = render(<StreamingDots />);
    const root = container.firstElementChild!;
    expect(root.tagName).toBe("SPAN");
    expect(root.children).toHaveLength(3);
    expect(root.className).toContain("flex");
  });

  it("switches to inline-flex when inline is set", () => {
    const { container } = render(<StreamingDots inline />);
    expect(container.firstElementChild!.className).toContain("inline-flex");
  });

  it("staggers animation-delay across the three dots", () => {
    const { container } = render(<StreamingDots />);
    const dots = Array.from(container.querySelectorAll("span > span"));
    expect(dots).toHaveLength(3);
    const delays = dots.map(
      (d) => (d as HTMLElement).style.animationDelay || "",
    );
    expect(delays).toEqual(["0ms", "160ms", "320ms"]);
  });

  it("is presentational and aria-hidden", () => {
    render(<StreamingDots />);
    const root = screen.getByRole("presentation", { hidden: true });
    expect(root).toBeTruthy();
    expect(root.getAttribute("aria-hidden")).toBe("true");
  });
});

describe("CancelStreamButton", () => {
  it("invokes onCancel when clicked", () => {
    const onCancel = vi.fn();
    render(<CancelStreamButton onCancel={onCancel} />);
    fireEvent.click(screen.getByLabelText(/stop generating reply/i));
    expect(onCancel).toHaveBeenCalled();
  });

  it("uses type=button so it doesn't submit ancestor forms", () => {
    render(<CancelStreamButton onCancel={() => {}} />);
    const btn = screen.getByLabelText(/stop generating reply/i);
    expect((btn as HTMLButtonElement).type).toBe("button");
  });
});
