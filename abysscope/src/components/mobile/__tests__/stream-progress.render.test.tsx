// @vitest-environment happy-dom
import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { StreamProgress } from "../mobile-chat-streaming";

afterEach(() => {
  vi.useRealTimers();
});

describe("StreamProgress", () => {
  it("renders nothing when streaming is false", () => {
    const { container } = render(
      <StreamProgress streaming={false} hasText={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows just the dots for the first few seconds when text is empty", () => {
    vi.useFakeTimers();
    render(<StreamProgress streaming hasText={false} />);
    // First 30s: no "Still thinking" label yet.
    expect(screen.queryByText(/Still thinking/)).toBeNull();
  });

  it("flips to 'Still thinking · Ns' once 30 seconds elapse (empty bubble)", () => {
    vi.useFakeTimers();
    render(<StreamProgress streaming hasText={false} />);
    act(() => {
      vi.advanceTimersByTime(30_000);
    });
    expect(screen.getByText(/Still thinking · 30s/)).toBeTruthy();
  });

  it("hides the elapsed counter until 3 seconds when text is streaming", () => {
    vi.useFakeTimers();
    const { container } = render(<StreamProgress streaming hasText />);
    // The counter span is rendered but starts at opacity-0; the
    // class is observable in the DOM.
    const counter = container.querySelector(
      ".tabular-nums.transition-opacity",
    );
    expect(counter).not.toBeNull();
    expect(counter!.className).toContain("opacity-0");
    act(() => {
      vi.advanceTimersByTime(3_500);
    });
    expect(counter!.className).toContain("opacity-100");
  });

  it("wires the optional cancel button when streaming", () => {
    const onCancel = vi.fn();
    render(<StreamProgress streaming hasText={false} onCancel={onCancel} />);
    fireEvent.click(screen.getByLabelText(/stop generating reply/i));
    expect(onCancel).toHaveBeenCalled();
  });
});
