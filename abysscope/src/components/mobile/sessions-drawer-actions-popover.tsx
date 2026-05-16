"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { Pencil, Trash2 } from "lucide-react";

/**
 * Portal-rendered actions menu for a session row.
 *
 * Earlier revisions positioned the menu absolutely inside the row's
 * ``<li>`` element. That works fine for top-of-list rows, but the
 * surrounding ``<ul className="overflow-y-auto">`` clipped the popup
 * for any row near the bottom of the scroll container — the user
 * reported "우클릭 되는데 하단은 안나옴".
 *
 * Rendering through ``createPortal`` to ``document.body`` escapes the
 * scroll container, and positioning via ``getBoundingClientRect``
 * keeps the menu visually anchored to the trigger button. We flip
 * above the anchor when there isn't enough room below so the menu
 * never falls off the viewport edge on short phones.
 */
export function SessionActionsPopover({
  anchor,
  onClose,
  onRename,
  onDelete,
}: {
  anchor: { top: number; left: number; bottom: number; right: number };
  onClose: () => void;
  onRename: () => void;
  onDelete: () => void;
}) {
  const [mounted, setMounted] = React.useState(false);
  const menuRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  React.useEffect(() => {
    const onPointer = (event: MouseEvent | TouchEvent) => {
      if (!menuRef.current) return;
      if (menuRef.current.contains(event.target as Node)) return;
      onClose();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("touchstart", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("touchstart", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  if (!mounted) return null;

  const MENU_WIDTH = 176;
  const MENU_HEIGHT = 96;
  const GAP = 6;

  const viewportWidth =
    typeof window === "undefined" ? 360 : window.innerWidth;
  const viewportHeight =
    typeof window === "undefined" ? 640 : window.innerHeight;

  // Flip above the anchor when there isn't enough room below.
  const placeBelow = anchor.bottom + GAP + MENU_HEIGHT <= viewportHeight;
  const top = placeBelow
    ? Math.min(anchor.bottom + GAP, viewportHeight - MENU_HEIGHT - 8)
    : Math.max(anchor.top - GAP - MENU_HEIGHT, 8);
  // Align the menu's right edge with the trigger's right edge, but
  // pull it inside the viewport if that would clip the left side.
  const right = Math.max(
    8,
    Math.min(viewportWidth - anchor.right, viewportWidth - MENU_WIDTH - 8),
  );

  return createPortal(
    <div
      ref={menuRef}
      role="menu"
      className="fixed z-50 w-44 rounded-md border bg-popover py-1 text-sm text-popover-foreground shadow-md"
      style={{ top, right }}
    >
      <button
        type="button"
        role="menuitem"
        onClick={onRename}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted"
      >
        <Pencil className="size-4" />
        <span>Rename</span>
      </button>
      <button
        type="button"
        role="menuitem"
        onClick={onDelete}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-destructive hover:bg-destructive/10"
      >
        <Trash2 className="size-4" />
        <span>Delete</span>
      </button>
    </div>,
    document.body,
  );
}
