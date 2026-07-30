# Archive → navigable directory (Windows-Explorer model)

Turn the flat archive table into a browsable filesystem over the existing two-level
taxonomy (category folders ▸ subcategory folders ▸ documents), with in-place power
features and a folder-scoped chat.

**Presentable plan (interactive mockup):** https://claude.ai/code/artifact/b51f8fc1-01aa-407c-a18d-3228211e3a4a

## Feasibility (verified against the code)

- `GET /documents` already supports `class` (subclass-aware via `expand_class_slugs`),
  `primary=true`, `status`, keyset `cursor` — **folder browse is pure frontend.**
- `retrieve(..., class_slug=...)` already scopes to a class + its children
  (`_resolve_scope`, `app/services/retrieval.py`) — **folder chat is 90% built**; only
  the plumbing above it (`MessageCreate` → `conversations.chat`/`chat_stream` →
  `synthesize`) doesn't pass a class scope yet.
- `buildFolderTree` (`web/src/features/archive/taxonomy.ts`) already assembles
  parent ▸ child with aggregate counts. Reuse it for the tree pane + folder grid.

## Frontend work (the bulk; ships on today's API)

- **Routing:** `/archive/[[...folder]]` already a catch-all → make `resolveFolder`
  a `resolvePath(segments[])` so a path is `financial/invoices`. Breadcrumb from the path.
- **New/changed components:** `folder-grid.tsx` (tiles w/ peek thumbnails), `folder-tree.tsx`
  (nav pane — was removed in the table rework; reintroduce), `breadcrumb-bar.tsx`
  (address bar: clickable + copy path, Back/Up), `preview-pane.tsx` (selection-follow
  card), `quick-look.tsx` (Space → first page + card modal), `context-menu.tsx`
  (folders + docs), selection state + `selection-bar.tsx` (multi-select bulk move/delete/ask),
  view-mode switch (Icons / List / Details — extend the existing SegmentedControl).
  Drag-to-refile via reused `set_primary` (dnd-kit reintroduce or HTML5 DnD).
- **Motion:** reuse the just-shipped `.pressable` / `usePresence` / pop-in; folder tiles
  rise on hover, chat dock springs from its trigger. All reduced-motion gated.

## Backend changes

| # | Change | Effort | Notes |
| --- | --- | --- | --- |
| 1 | **Folder-scoped chat** — `scope="folder"` + `class_slug` on `MessageCreate`; thread → `conversations.chat`/`chat_stream` → `synthesize(class_slug=)` → the `retrieve()` call | S | Headline. `retrieve()` already accepts `class_slug`. Add offline test. |
| 2 | `?class=X&include_subclasses=false` on `/documents` | XS | Show a parent's own docs vs. its subfolders. Deferrable (split only at leaves at first). |
| 3 | `?q=` on `/documents` (ILIKE title/filename or FTS) | S | Whole-folder search beyond loaded pages. Client-side filter is the interim. |
| 4 | `document_pins` / `folder_pins` table + endpoints (Starred / Quick Access) | M | Alembic migration. Phase 3. |
| 5 | `GET /classes/{id}/summary` (count, bytes, date range, status breakdown, top parties) | M | Folder Properties. Much derives client-side. Phase 3. |
| — | Recently-opened | none | Browser-local history. |

## Phasing

- **Phase 1 — The directory (frontend only):** ✅ **DONE.** Nested browse + routing,
  folder grid, tree pane, Quick Look + preview pane (A–C); context menus + multi-select
  + bulk move/delete (E); drag-to-refile (F, pulled forward from Phase 2).
  Icons/List/Details view modes (D) shipped too: Table→**Details**, Gallery→**Icons**,
  plus a new column-flow **List** (names only) that shares selection/menu/drag with
  the table. The choice persists per browser.
- **Phase 2 — Ask this folder:** ✅ **DONE for the headline.** Backend #1 shipped
  (`scope:"folder"` + `class_slug` → `synthesize(class_slug=)` → every `retrieve()`
  pass, agent `search` tool included) and the docked, folder-scoped chat panel ships
  with it. **Still open:** smart folders (Recent [local], By vendor/party
  [client-side], This month).
- **Phase 3 — Memory & depth:** Starred/Quick Access (#4), Folder Properties (#5),
  in-folder server search (#3), sort/group refinements.

## Open questions for the owner

- Tree pane always-on (desktop), or a toggle? (Explorer keeps it; costs horizontal room.)
- Reintroduce drag-and-drop (dnd-kit) or keep the "Move to…" menu + drag as additive?
- Phase 1 first (feel the directory), or go straight for "Ask this folder"?
