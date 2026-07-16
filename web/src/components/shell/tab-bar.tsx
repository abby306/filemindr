"use client";

/**
 * TabBar — mobile/tablet primary navigation (< lg, where the sidebar is): a
 * fixed bottom bar with Upload / Archive / Ask, and a More sheet holding the
 * secondary destinations (Review with its badge, Analytics, Billing) plus the
 * account bits (backend status + account switcher). Targets ≥44px throughout;
 * the bar respects the home-indicator safe area.
 */

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { MoreHorizontal } from "lucide-react";
import clsx from "clsx";

import { AccountSwitcher } from "@/components/shell/account-switcher";
import { BackendStatus } from "@/components/shell/backend-status";
import { Sheet } from "@/components/ui/sheet";
import { PRIMARY_NAV, SECONDARY_NAV, isActive, type NavItem } from "@/lib/nav";
import {
  feedHasProcessing,
  useDocumentsFeed,
  useReviewCount,
} from "@/features/upload/queries";

/** The bar shows the three everyday destinations; Review moves into More. */
const BAR_NAV = PRIMARY_NAV.filter((item) => item.href !== "/review");
const REVIEW_NAV = PRIMARY_NAV.find((item) => item.href === "/review");
const MORE_NAV: NavItem[] = [...(REVIEW_NAV ? [REVIEW_NAV] : []), ...SECONDARY_NAV];

export function TabBar() {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);
  const { data: feed } = useDocumentsFeed();
  const { data: review } = useReviewCount(feedHasProcessing(feed));

  const moreActive = MORE_NAV.some((item) => isActive(item, pathname));
  const reviewCount = review?.count ?? 0;

  return (
    <>
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden"
      >
        {BAR_NAV.map((item) => {
          const active = isActive(item, pathname);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={clsx(
                "flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5",
                active ? "text-accent-text" : "text-text-3",
              )}
            >
              <Icon aria-hidden className="size-5" strokeWidth={active ? 2.25 : 1.75} />
              <span className="type-caption">{item.label}</span>
            </Link>
          );
        })}
        <button
          type="button"
          onClick={() => setMoreOpen(true)}
          aria-expanded={moreOpen}
          aria-label={
            reviewCount > 0 ? `More (${reviewCount} awaiting review)` : "More"
          }
          className={clsx(
            "relative flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5",
            moreActive ? "text-accent-text" : "text-text-3",
          )}
        >
          <span className="relative">
            <MoreHorizontal aria-hidden className="size-5" strokeWidth={moreActive ? 2.25 : 1.75} />
            {reviewCount > 0 ? (
              <span
                aria-hidden
                className="absolute -right-1.5 -top-1 size-2 rounded-full bg-warn"
              />
            ) : null}
          </span>
          <span className="type-caption">More</span>
        </button>
      </nav>

      <Sheet open={moreOpen} onClose={() => setMoreOpen(false)} title="More">
        <nav aria-label="Secondary" className="flex flex-col gap-0.5">
          {MORE_NAV.map((item) => {
            const active = isActive(item, pathname);
            const Icon = item.icon;
            const isReview = item.href === "/review";
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMoreOpen(false)}
                aria-current={active ? "page" : undefined}
                className={clsx(
                  "flex min-h-12 items-center gap-3 rounded-md px-3 type-subhead transition-colors",
                  active
                    ? "bg-accent-50 text-accent-text"
                    : "text-text-1 hover:bg-surface-2",
                )}
              >
                <Icon aria-hidden className="size-[18px]" strokeWidth={1.75} />
                {item.label}
                {isReview && reviewCount > 0 ? (
                  <span
                    className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-warn/15 px-1.5 type-caption text-warn-text"
                    aria-label={`${reviewCount}${review?.hasMore ? "+" : ""} awaiting review`}
                  >
                    {reviewCount}
                    {review?.hasMore ? "+" : ""}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </nav>

        <div className="mt-3 flex items-center justify-between gap-3 border-t border-border pt-3">
          <BackendStatus />
          <AccountSwitcher />
        </div>
      </Sheet>
    </>
  );
}
