"use client";

/**
 * Finder-style navigation rail. Primary destinations up top, secondary (usage)
 * pinned lower. Renders the same markup for desktop (persistent column) and the
 * mobile drawer; the parent controls visibility. `onNavigate` lets the drawer
 * close on selection.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
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
  onNavigate,
}: {
  item: NavItem;
  badge?: number;
  badgeMore?: boolean;
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
      className={clsx(
        "flex items-center gap-3 rounded-md px-3 py-2 type-subhead transition-colors",
        "min-h-11", // ≥44px touch target
        active
          ? "bg-accent-50 text-accent-text shadow-[inset_2px_0_0_0_var(--accent)]"
          : "text-text-2 hover:bg-surface-2 hover:text-text-1",
      )}
    >
      <Icon aria-hidden className="size-[18px] shrink-0" strokeWidth={active ? 2.25 : 1.75} />
      <span>{item.label}</span>
      {badge && badge > 0 ? (
        <span
          className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-warn/15 px-1.5 type-caption text-warn"
          aria-label={`${badge}${badgeMore ? "+" : ""} awaiting review`}
        >
          {badge}
          {badgeMore ? "+" : ""}
        </span>
      ) : null}
    </Link>
  );
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { data: feed } = useDocumentsFeed();
  const { data: review } = useReviewCount(feedHasProcessing(feed));

  return (
    <nav
      aria-label="Primary"
      className="flex h-full flex-col gap-1 overflow-y-auto p-3"
    >
      <div className="flex flex-col gap-0.5">
        {PRIMARY_NAV.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            badge={item.href === "/review" ? review?.count : undefined}
            badgeMore={item.href === "/review" ? review?.hasMore : undefined}
            onNavigate={onNavigate}
          />
        ))}
      </div>

      <div className="mt-auto flex flex-col gap-0.5 pt-3">
        <p className="px-3 pb-1 type-caption uppercase text-text-3">Account</p>
        {SECONDARY_NAV.map((item) => (
          <NavLink key={item.href} item={item} onNavigate={onNavigate} />
        ))}
      </div>
    </nav>
  );
}
