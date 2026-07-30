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
 * By default the browse view hides *system* folders that hold no documents (the
 * seeded taxonomy is much wider than any one archive). Custom folders always
 * show: the user made them deliberately, and a folder that disappeared the
 * moment it was created would be unnameable and undeletable. Pass `includeEmpty`
 * for assignment surfaces (the move-to-folder menu) where every class is a
 * valid target.
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
      // Hide empty *system* subfolders from browse (not from assignment).
      const children = includeEmpty
        ? allChildren
        : allChildren.filter((c) => c.document_count > 0 || !c.is_system);
      return { cls, children, totalCount };
    })
    .filter(
      (node) =>
        includeEmpty ||
        node.totalCount > 0 ||
        !node.cls.is_system ||
        node.children.length > 0,
    );
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

/* -----------------------------------------------------------------------------
   Directory model — walk the taxonomy like a filesystem. Slugs are unique per
   account, so a single-segment URL (/archive/{slug}) still identifies a node;
   the parent/child hierarchy is derived from the class tree for breadcrumbs and
   "up" navigation. A node is a *folder* (show subfolder tiles) when it's the
   root or a parent that has child folders; otherwise it's a *leaf* (show docs).
   ----------------------------------------------------------------------------- */

export interface Crumb {
  label: string;
  href: string;
  /** class slug for a folder crumb (used to target drag/drop, context menus). */
  slug?: string;
}

/** Ancestor trail for the address bar: Archive ▸ Parent ▸ Child. */
export function breadcrumbFor(filter: FolderFilter, classes: ClassInfo[]): Crumb[] {
  const root: Crumb = { label: "Archive", href: "/archive" };
  if (filter.kind === "all") return [{ label: "All documents", href: "/archive" }];
  if (filter.kind === "needs_review") {
    return [root, { label: "Needs review", href: folderHref(filter) }];
  }
  const cls = classes.find((c) => c.slug === filter.slug);
  if (!cls) {
    return [root, { label: filter.slug, href: folderHref(filter), slug: filter.slug }];
  }
  const crumbs: Crumb[] = [root];
  if (cls.parent_slug) {
    const parent = classes.find((c) => c.slug === cls.parent_slug);
    if (parent) {
      crumbs.push({
        label: parent.name,
        href: folderHref({ kind: "class", slug: parent.slug }),
        slug: parent.slug,
      });
    }
  }
  crumbs.push({ label: cls.name, href: folderHref(filter), slug: cls.slug });
  return crumbs;
}

/** The parent whose folder view "up" leads to (or /archive at the top). */
export function parentHref(filter: FolderFilter, classes: ClassInfo[]): string {
  const trail = breadcrumbFor(filter, classes);
  return trail.length > 1 ? trail[trail.length - 2].href : "/archive";
}

export interface FolderTile {
  /** Class id — folder rename/delete address the class, not the slug. */
  id: string;
  slug: string;
  name: string;
  count: number;
  isSystem: boolean;
  hasChildren: boolean;
}

function toTile(cls: ClassInfo, count: number, hasChildren: boolean): FolderTile {
  return {
    id: cls.id,
    slug: cls.slug,
    name: cls.name,
    count,
    isSystem: cls.is_system,
    hasChildren,
  };
}

/**
 * The folder tiles to show *inside* a node, or `null` when the node is a leaf
 * (render its documents instead). Root → parent categories; a parent with child
 * folders → those children; anything else → leaf.
 */
export function folderTilesFor(
  filter: FolderFilter,
  tree: FolderNode[],
): FolderTile[] | null {
  if (filter.kind === "all") {
    return tree.map((n) => toTile(n.cls, n.totalCount, n.children.length > 0));
  }
  if (filter.kind === "needs_review") return null;
  const node = tree.find((n) => n.cls.slug === filter.slug);
  if (node && node.children.length > 0) {
    return node.children.map((c) => toTile(c, c.document_count, false));
  }
  return null; // childless parent, a child slug, or an empty custom folder
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
