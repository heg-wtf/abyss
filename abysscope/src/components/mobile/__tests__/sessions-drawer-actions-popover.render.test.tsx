// @vitest-environment happy-dom
import { describe, expect, it, vi, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  cleanup,
} from "@testing-library/react";
import { SessionActionsPopover } from "../sessions-drawer-actions-popover";

const ANCHOR = { top: 100, left: 50, bottom: 140, right: 200 };

afterEach(() => {
  cleanup();
});

describe("SessionActionsPopover", () => {
  it("renders Rename and Delete menu items", () => {
    render(
      <SessionActionsPopover
        anchor={ANCHOR}
        onClose={() => {}}
        onRename={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.getByText("Rename")).toBeTruthy();
    expect(screen.getByText("Delete")).toBeTruthy();
  });

  it("invokes onRename / onDelete from the matching menu item", () => {
    const onRename = vi.fn();
    const onDelete = vi.fn();
    render(
      <SessionActionsPopover
        anchor={ANCHOR}
        onClose={() => {}}
        onRename={onRename}
        onDelete={onDelete}
      />,
    );
    fireEvent.click(screen.getByText("Rename"));
    expect(onRename).toHaveBeenCalled();
    fireEvent.click(screen.getByText("Delete"));
    expect(onDelete).toHaveBeenCalled();
  });

  it("closes on outside mousedown (click outside the popover)", () => {
    const onClose = vi.fn();
    render(
      <SessionActionsPopover
        anchor={ANCHOR}
        onClose={onClose}
        onRename={() => {}}
        onDelete={() => {}}
      />,
    );
    fireEvent.mouseDown(document.body);
    expect(onClose).toHaveBeenCalled();
  });

  it("does not close when clicking inside the popover", () => {
    const onClose = vi.fn();
    render(
      <SessionActionsPopover
        anchor={ANCHOR}
        onClose={onClose}
        onRename={() => {}}
        onDelete={() => {}}
      />,
    );
    fireEvent.mouseDown(screen.getByText("Rename"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes when Escape is pressed", () => {
    const onClose = vi.fn();
    render(
      <SessionActionsPopover
        anchor={ANCHOR}
        onClose={onClose}
        onRename={() => {}}
        onDelete={() => {}}
      />,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("flips above the anchor when there isn't room below the viewport", () => {
    // Anchor near the bottom of the viewport — should place above.
    Object.defineProperty(window, "innerHeight", { value: 200, configurable: true });
    const lowAnchor = { top: 180, left: 100, bottom: 195, right: 220 };
    render(
      <SessionActionsPopover
        anchor={lowAnchor}
        onClose={() => {}}
        onRename={() => {}}
        onDelete={() => {}}
      />,
    );
    const menu = document.querySelector('[role="menu"]') as HTMLElement;
    // top should be lower than anchor.top - MENU_HEIGHT (96) - GAP (6)
    // ≈ 78, so menu top should be ≤ 78 to be above the anchor.
    expect(parseInt(menu.style.top, 10)).toBeLessThan(lowAnchor.top);
  });
});
