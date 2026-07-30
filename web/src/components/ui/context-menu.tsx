"use client";

/**
 * ContextMenu — a pointer-anchored menu (Explorer's right-click). Open it with
 * an `{x, y}` anchor from a `contextmenu` event; it renders fixed at that point,
 * flips against the viewport edges, dismisses on outside pointer-down / Escape /
 * scroll, and animates in from its own corner (`.animate-pop-in`).
 *
 *   const [menu, setMenu] = useState<MenuAnchor | null>(null);
 *   <div onContextMenu={(e) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY }); }} />
 *   <ContextMenu anchor={menu} items={items} onClose={() => setMenu(null)} />
 *
 * Items may carry a `submenu` (used for "Move to folder…", whose list is long
 * enough to scroll). Positioning is done on a ref callback rather than in an
 * effect — measuring the rendered box can't happen before paint, and writing it
 * straight to `style` keeps it out of React state (see the set-state-in-effect
 * lint rule).
 */

import { useCallback, useRef, useState, type ReactNode } from "react";
import { Check, ChevronRight, type LucideIcon } from "lucide-react";
import clsx from "clsx";

import { useDismiss } from "@/lib/use-dismiss";
import { usePresence } from "@/lib/use-presence";

/** Viewport coordinates the menu opens at (an event's clientX/clientY). */
export interface MenuAnchor {
  x: number;
  y: number;
}

export interface MenuItem {
  key: string;
  label: string;
  icon?: LucideIcon;
  onSelect?: () => void;
  /** Renders a nested panel instead of acting on select. */
  submenu?: MenuItem[];
  danger?: boolean;
  disabled?: boolean;
  /** Trailing ✓ (the document's current folder in a move submenu). */
  checked?: boolean;
  /** Draw a divider above this item. */
  separatorBefore?: boolean;
  /** Quiet right-aligned hint ("Space", "⏎", "System folder"). */
  hint?: string;
  /** Nested one level (a subfolder under its parent in the move submenu). */
  indent?: boolean;
}

const MARGIN = 8;
const EXIT_MS = 120;

export function ContextMenu({
  anchor,
  items,
  onClose,
  label = "Context menu",
}: {
  anchor: MenuAnchor | null;
  items: MenuItem[];
  onClose: () => void;
  label?: string;
}) {
  const open = anchor !== null;
  const { mounted, state } = usePresence(open, EXIT_MS);
  const ref = useRef<HTMLDivElement>(null);
  useDismiss(ref, onClose, open);

  const x = anchor?.x ?? 0;
  const y = anchor?.y ?? 0;

  // Place after layout, straight onto the node: clamp into the viewport and
  // flip the transform-origin so the pop-in grows from the pointer.
  const place = useCallback(
    (el: HTMLDivElement | null) => {
      ref.current = el;
      if (!el) return;
      const box = el.getBoundingClientRect();
      const flipX = x + box.width + MARGIN > window.innerWidth;
      const flipY = y + box.height + MARGIN > window.innerHeight;
      const left = flipX ? Math.max(MARGIN, x - box.width) : x;
      const top = flipY ? Math.max(MARGIN, y - box.height) : y;
      el.style.left = `${left}px`;
      el.style.top = `${top}px`;
      el.style.transformOrigin = `${flipX ? "right" : "left"} ${flipY ? "bottom" : "top"}`;
    },
    [x, y],
  );

  if (!mounted) return null;

  return (
    <div
      ref={place}
      role="menu"
      aria-label={label}
      style={{ left: x, top: y }}
      onContextMenu={(e) => e.preventDefault()}
      className={clsx(
        "fixed z-50 min-w-52 rounded-lg border border-border bg-surface p-1 shadow-e3",
        state === "closing" ? "animate-pop-out" : "animate-pop-in",
      )}
    >
      <MenuList items={items} onClose={onClose} />
    </div>
  );
}

/** The item list — shared by the root menu and any submenu panel. */
function MenuList({ items, onClose }: { items: MenuItem[]; onClose: () => void }) {
  return (
    <>
      {items.map((item) => (
        <div key={item.key}>
          {item.separatorBefore ? (
            <div aria-hidden className="my-1 h-px bg-border" />
          ) : null}
          {item.submenu ? (
            <SubmenuItem item={item} onClose={onClose} />
          ) : (
            <MenuButton item={item} onClose={onClose} />
          )}
        </div>
      ))}
    </>
  );
}

const ROW =
  "flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left type-subhead transition-colors";

function MenuButton({ item, onClose }: { item: MenuItem; onClose: () => void }) {
  const Icon = item.icon;
  return (
    <button
      type="button"
      role="menuitem"
      disabled={item.disabled}
      onClick={() => {
        onClose();
        item.onSelect?.();
      }}
      className={clsx(
        ROW,
        item.indent && "pl-6",
        item.disabled
          ? "cursor-default text-text-3"
          : item.danger
            ? "text-danger hover:bg-danger/10"
            : "text-text-1 hover:bg-surface-2",
      )}
    >
      {Icon ? <Icon aria-hidden className="size-4 shrink-0" strokeWidth={1.75} /> : null}
      <span className="truncate">{item.label}</span>
      <Trailing item={item} />
    </button>
  );
}

function SubmenuItem({ item, onClose }: { item: MenuItem; onClose: () => void }) {
  const [open, setOpen] = useState(false);
  const Icon = item.icon;

  return (
    <div
      className="relative"
      onPointerEnter={() => setOpen(true)}
      onPointerLeave={() => setOpen(false)}
    >
      <button
        type="button"
        role="menuitem"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={clsx(ROW, "text-text-1 hover:bg-surface-2", open && "bg-surface-2")}
      >
        {Icon ? <Icon aria-hidden className="size-4 shrink-0" strokeWidth={1.75} /> : null}
        <span className="truncate">{item.label}</span>
        <ChevronRight aria-hidden className="ml-auto size-3.5 shrink-0 text-text-3" />
      </button>

      {open ? (
        <div
          role="menu"
          aria-label={item.label}
          className="animate-pop-in absolute left-full top-0 z-10 -mt-1 ml-0.5 max-h-72 w-56 origin-top-left overflow-y-auto rounded-lg border border-border bg-surface p-1 shadow-e3"
        >
          <MenuList items={item.submenu ?? []} onClose={onClose} />
        </div>
      ) : null}
    </div>
  );
}

function Trailing({ item }: { item: MenuItem }): ReactNode {
  if (item.checked) {
    return <Check aria-hidden className="ml-auto size-3.5 shrink-0 text-text-3" />;
  }
  if (item.hint) {
    return <span className="ml-auto shrink-0 type-caption text-text-3">{item.hint}</span>;
  }
  return null;
}
