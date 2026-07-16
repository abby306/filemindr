/**
 * Navigation model for the Finder-style rail. Screens map to the routes specced
 * in FRONTEND.md §"Screens". Feature content is stubbed in this milestone — the
 * rail, routing, and active-state are the deliverable.
 */

import {
  BarChart3,
  CreditCard,
  FolderOpen,
  MessageSquareText,
  Upload,
  Inbox,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** True when the current pathname should be matched by exact equality only. */
  exact?: boolean;
}

export const PRIMARY_NAV: NavItem[] = [
  { href: "/", label: "Upload", icon: Upload, exact: true },
  { href: "/archive", label: "Archive", icon: FolderOpen },
  { href: "/review", label: "Review", icon: Inbox },
  { href: "/chat", label: "Ask", icon: MessageSquareText },
];

/** Billing UI is a hosted-product surface; self-hosted installs (quotas off)
 * hide it from the rail. Set NEXT_PUBLIC_ENABLE_BILLING=1 to show it. */
const BILLING_ENABLED = process.env.NEXT_PUBLIC_ENABLE_BILLING === "1";

export const SECONDARY_NAV: NavItem[] = [
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  ...(BILLING_ENABLED
    ? [{ href: "/billing", label: "Billing", icon: CreditCard } satisfies NavItem]
    : []),
];

/** Whether a nav item is active for the given pathname. */
export function isActive(item: NavItem, pathname: string): boolean {
  if (item.exact) return pathname === item.href;
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}
