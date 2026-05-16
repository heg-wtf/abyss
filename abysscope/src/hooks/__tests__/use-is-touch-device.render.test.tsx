// @vitest-environment happy-dom
import { describe, expect, it, afterEach, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useIsTouchDevice } from "../use-is-touch-device";

type MqlListener = (event: MediaQueryListEvent) => void;

function installMatchMedia(matches: boolean): {
  setMatches: (value: boolean) => void;
} {
  let current = matches;
  const listeners = new Set<MqlListener>();
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: current,
    media: query,
    onchange: null,
    addEventListener: vi.fn((_: string, fn: MqlListener) => listeners.add(fn)),
    removeEventListener: vi.fn((_: string, fn: MqlListener) =>
      listeners.delete(fn),
    ),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as typeof window.matchMedia;
  return {
    setMatches: (value: boolean) => {
      current = value;
      for (const fn of listeners) {
        fn({ matches: value } as MediaQueryListEvent);
      }
    },
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useIsTouchDevice", () => {
  it("returns true when the media query matches", () => {
    installMatchMedia(true);
    const { result } = renderHook(() => useIsTouchDevice());
    expect(result.current).toBe(true);
  });

  it("returns false when the media query does not match", () => {
    installMatchMedia(false);
    const { result } = renderHook(() => useIsTouchDevice());
    expect(result.current).toBe(false);
  });

  it("queries the hover:none + pointer:coarse combination", () => {
    installMatchMedia(false);
    renderHook(() => useIsTouchDevice());
    expect(window.matchMedia).toHaveBeenCalledWith(
      "(hover: none) and (pointer: coarse)",
    );
  });

  it("unsubscribes the change listener on unmount", () => {
    installMatchMedia(false);
    const queryResult = (window.matchMedia as ReturnType<typeof vi.fn>).mock
      .results;
    const { unmount } = renderHook(() => useIsTouchDevice());
    const mql = queryResult[0].value as {
      removeEventListener: ReturnType<typeof vi.fn>;
    };
    unmount();
    expect(mql.removeEventListener).toHaveBeenCalled();
  });
});
