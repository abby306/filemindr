"use client";

/**
 * Finder-style navigation rail. Primary destinations up top, secondary (usage)
 * pinned lower, and a collapse toggle at the foot: collapsed, the rail is an
 * icon strip (labels in tooltips, the review badge becomes a dot) so content
 * runs full width. Renders the same markup for desktop and the mobile drawer;
 * the parent controls visibility. `onNavigate` lets the drawer close on
 * selection.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import clsx from "clsx";

import { PRIMARY_NAV, SECONDARY_NAV, isActive, type NavItem } from "@/lib/nav";
import {
  feedHasProcessing,
  useDocumentsFeed,
  useReviewCount,
} from "@/features/upload/queries";

function NavLink({
  item,
  badge,
  badgeMore,
  collapsed,
  onNavigate,
}: {
  item: NavItem;
  badge?: number;
  badgeMore?: boolean;
  collapsed?: boolean;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const active = isActive(item, pathname);
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      title={collapsed ? item.label : undefined}
      className={clsx(
        "relative flex items-center gap-3 rounded-md py-2 type-subhead transition-colors",
        "min-h-11", // ≥44px touch target
        collapsed ? "justify-center px-0" : "px-3",
        active
          ? "bg-accent-50 text-accent-text shadow-[inset_2px_0_0_0_var(--accent)]"
          : "text-text-2 hover:bg-surface-2 hover:text-text-1",
      )}
    >
      <Icon aria-hidden className="size-[18px] shrink-0" strokeWidth={active ? 2.25 : 1.75} />
      {collapsed ? (
        badge && badge > 0 ? (
          <span
            aria-label={`${badge}${badgeMore ? "+" : ""} awaiting review`}
            className="absolute right-2 top-2 size-2 rounded-full bg-warn"
          />
        ) : null
      ) : (
        <>
          <span>{item.label}</span>
          {badge && badge > 0 ? (
            <span
              className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-warn/15 px-1.5 type-caption text-warn-text"
              aria-label={`${badge}${badgeMore ? "+" : ""} awaiting review`}
            >
              {badge}
              {badgeMore ? "+" : ""}
            </span>
          ) : null}
        </>
      )}
    </Link>
  );
}

export function Sidebar({
  collapsed,
  onToggleCollapse,
  onNavigate,
}: {
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  onNavigate?: () => void;
}) {
  const { data: feed } = useDocumentsFeed();
  const { data: review } = useReviewCount(feedHasProcessing(feed));

  return (
    <nav
      aria-label="Primary"
      className={clsx("flex h-full flex-col gap-1 overflow-y-auto", collapsed ? "p-2" : "p-3")}
    >
      {onToggleCollapse ? (
        <button
          type="button"
          onClick={onToggleCollapse}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={clsx(
            "mb-1 flex min-h-9 items-center rounded-md py-2 text-text-3 transition-colors hover:bg-surface-2 hover:text-text-1",
            collapsed ? "justify-center px-0" : "justify-end px-3",
          )}
        >
          {collapsed ? (
            <PanelLeftOpen aria-hidden className="size-[18px] shrink-0" strokeWidth={1.75} />
          ) : (
            <PanelLeftClose aria-hidden className="size-[18px] shrink-0" strokeWidth={1.75} />
          )}
        </button>
      ) : null}
      <div className="flex flex-col gap-0.5">
        {PRIMARY_NAV.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            badge={item.href === "/review" ? review?.count : undefined}
            badgeMore={item.href === "/review" ? review?.hasMore : undefined}
            collapsed={collapsed}
            onNavigate={onNavigate}
          />
        ))}
      </div>

      <div className="mt-auto flex flex-col gap-0.5 pt-3">
        {!collapsed ? (
          <p className="px-3 pb-1 type-caption uppercase text-text-3">Account</p>
        ) : null}
        {SECONDARY_NAV.map((item) => (
          <NavLink key={item.href} item={item} collapsed={collapsed} onNavigate={onNavigate} />
        ))}
      </div>
    </nav>
  );
}
