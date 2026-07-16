/**
 * Archive taxonomy helpers — turn the flat `ClassInfo[]` from `GET /classes`
 * into the two-level FolderTree (parents ▸ children), define the smart folders
 * that map to real API filters, and provide presentational metadata (parent
 * tint, status badge look). No business logic that a native client would need
 * to reuse lives here — grouping the catalog for display is view concern.
 */

import {
  FolderClosed,
  Inbox,
  Layers,
  type LucideIcon,
} from "lucide-react";

import type { ClassInfo, DocumentStatus } from "@/lib/api/types";

/** What documents the main pane shows — each maps 1:1 to a supported API query. */
export type FolderFilter =
  | { kind: "all" }
  | { kind: "needs_review" }
  | { kind: "class"; slug: string };

/** URL segment (under /archive/…) that selects a smart folder. */
const NEEDS_REVIEW_SEGMENT = "needs-review";

export interface SmartFolder {
  segment: string | null; // null → /archive (All)
  label: string;
  icon: LucideIcon;
  filter: FolderFilter;
}

export const SMART_FOLDERS: SmartFolder[] = [
  { segment: null, label: "All documents", icon: Layers, filter: { kind: "all" } },
  {
    segment: NEEDS_REVIEW_SEGMENT,
    label: "Needs review",
    icon: Inbox,
    filter: { kind: "needs_review" },
  },
];

export interface FolderNode {
  cls: ClassInfo;
  children: ClassInfo[];
  /** Aggregate count = own + children (children's docs also list under a parent). */
  totalCount: number;
}

/**
 * Group the catalog into parent folders with their subclass children. Classes
 * whose parent isn't present are treated as top-level. Parents sort system-first
 * then by name (matching the API order); children by name.
 *
 * By default the browse view only surfaces folders that actually hold
 * documents: empty subclasses are hidden, and a parent is shown only when it
 * (or a child) has documents. Pass `includeEmpty` for assignment surfaces
 * (the move-to-folder menu) where every class must be a valid target.
 */
export function buildFolderTree(
  classes: ClassInfo[],
  { includeEmpty = false }: { includeEmpty?: boolean } = {},
): FolderNode[] {
  const byId = new Map(classes.map((c) => [c.id, c]));
  const childrenOf = new Map<string, ClassInfo[]>();
  const roots: ClassInfo[] = [];

  for (const cls of classes) {
    const parentPresent = cls.parent_id != null && byId.has(cls.parent_id);
    if (parentPresent) {
      const list = childrenOf.get(cls.parent_id!) ?? [];
      list.push(cls);
      childrenOf.set(cls.parent_id!, list);
    } else {
      roots.push(cls);
    }
  }

  const byName = (a: ClassInfo, b: ClassInfo) => a.name.localeCompare(b.name);
  return roots
    .sort((a, b) => Number(b.is_system) - Number(a.is_system) || byName(a, b))
    .map((cls) => {
      const allChildren = (childrenOf.get(cls.id) ?? []).sort(byName);
      const totalCount =
        cls.document_count + allChildren.reduce((n, c) => n + c.document_count, 0);
      // Hide empty subclasses from the browse chips (not from assignment).
      const children = includeEmpty
        ? allChildren
        : allChildren.filter((c) => c.document_count > 0);
      return { cls, children, totalCount };
    })
    .filter((node) => includeEmpty || node.totalCount > 0);
}

/** Resolve a URL folder segment to the filter + a stable selection key. */
export function resolveFolder(segment: string | undefined): {
  filter: FolderFilter;
  key: string;
} {
  if (!segment) return { filter: { kind: "all" }, key: "all" };
  if (segment === NEEDS_REVIEW_SEGMENT) {
    return { filter: { kind: "needs_review" }, key: "needs_review" };
  }
  return { filter: { kind: "class", slug: segment }, key: `class:${segment}` };
}

export function folderHref(filter: FolderFilter): string {
  switch (filter.kind) {
    case "all":
      return "/archive";
    case "needs_review":
      return `/archive/${NEEDS_REVIEW_SEGMENT}`;
    case "class":
      return `/archive/${filter.slug}`;
  }
}

export function filterKey(filter: FolderFilter): string {
  switch (filter.kind) {
    case "all":
      return "all";
    case "needs_review":
      return "needs_review";
    case "class":
      return `class:${filter.slug}`;
  }
}

export const CLASS_FOLDER_ICON: LucideIcon = FolderClosed;

/* -----------------------------------------------------------------------------
   Status display metadata (presentational). NOTE: the authoritative never-wait
   step labels ("Reading/Understanding/Filing/Filed") are specced to move
   server-side with the upload/ProcessingDock milestone; this map covers the
   archive's read-only badge until then. `tone` maps to a semantic token.
   ----------------------------------------------------------------------------- */
export type StatusTone = "ok" | "warn" | "danger" | "idle" | "accent";

export const STATUS_META: Record<
  DocumentStatus,
  { label: string; tone: StatusTone }
> = {
  received: { label: "Reading", tone: "accent" },
  ocr_done: { label: "Understanding", tone: "accent" },
  extracted: { label: "Filing", tone: "accent" },
  indexed: { label: "Filed", tone: "ok" },
  needs_review: { label: "Review", tone: "warn" },
  failed: { label: "Failed", tone: "danger" },
};

/** Non-terminal statuses — the never-wait model polls while any doc is here. */
export function isProcessing(status: DocumentStatus): boolean {
  return status === "received" || status === "ocr_done" || status === "extracted";
}
