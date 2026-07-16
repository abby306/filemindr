# FRONTEND.md — filemindr

Machine-readable design tokens + component/screen specs. **This is the design contract** — agents read this, not mockups. Edit token values here and in `web/src/app/globals.css` together (globals.css is the runtime source of truth; this file explains intent).

## Design v2 — "precision minimal" (current)

Aesthetic in one line: **the register of engineered products (ElevenLabs/Linear/Apple) with one highlighter.** Clean neutral surfaces; two colors carry meaning: **ink blue** for everything actionable, and the **amber highlighter reserved for provenance** — where the machine read. One type family. Motion is choreographed around the product's journey and fires once, on real state changes.

Design v1 ("Ink & Manila" — warm paper, Instrument Serif, manila cards, category folder colors) is **retired**. Do not reintroduce serif display type, paper textures, or per-folder color coding.

**Identity moves:**
1. **Wordmark**: lowercase `filemindr` in Geist 600, tight tracking, with the amber wash over "mind" (`.wordmark` + `.wordmark-mark`) — a highlighted word in a document. The only place color enters the brand.
2. **Provenance is the one bold moment**: citation chips carry an amber pin; clicking one washes the cited source region amber in 240ms (SourceGlow). Nothing else uses `--hl*`.
3. **The pipeline is the hero animation**: upload → four segments fill per real backend stage (shimmer on active, pop on complete) → "Filed" earns a drawn checkmark.

## Stack

Next.js (App Router, TS) · Tailwind v4 (tokens as CSS vars) · Framer Motion (available; most motion is CSS-first) · dnd-kit · TanStack Query. Fonts via `next/font/google`: **Geist** (everything) + **Geist Mono** (data voice: facts, ids, amounts, the trace).

**Architecture (locked):** pure thin client over the JSON+SSE API — no business logic in the web tier; every derived value is computed server-side so a future React Native app reuses the same API.

## Tokens (authoritative values in `web/src/app/globals.css`)

```
Light                              Dark (true-neutral, not black)
canvas      #FAFAFA               #0D0E12
surface     #FFFFFF               #16171C
surface-2   #F3F4F6               #1E2026
border      #E7E8EB               #2A2C33
text-1/2/3  #0C0D10/#55575E/#989AA3   #F2F3F5/#A6A8B1/#6E7078

accent      #2563EB (both modes)  — buttons, links, focus, selection, progress
accent-text #2059D4               #8AB0FF   — accent used AS text
accent-wash rgba(37,99,235,.08)   rgba(96,143,255,.13) — selected states
on-accent   #FFFFFF (both)

hl (provenance ONLY) #B78105 / wash rgba(255,211,61,.32)   dark #F2C744 / .16
ok/warn/danger  #16A34A/#D97706/#DC2626   dark #3ECF6E/#F5A623/#F87171
warn-text       #B45309 (warn used AS text, AA)            dark #F5A623

radius  6/8/10/12 + pill          shadows e1 (cards) / e2 (popovers) / e3 (modals)
motion  120ms micro · 160ms base · 220ms emphasis · 240ms sheets/provenance
        --ease-quiet / --ease-standard / --ease-spring
```

Rules: color never encodes folders/categories; status colors always ship with a label; `--hl*` never appears outside provenance; primary CTAs are `bg-accent text-on-accent`.

## Type scale (`.type-*` helpers in globals.css — all Geist)

| helper | size/line/weight | use |
|---|---|---|
| display | 32/38/600 −0.02em | page titles |
| title1 | 24/30/600 | section heads |
| title2 | 18/24/600 | sub-sections |
| record / title3 | 16/22 · 15/22 /600 | card & doc titles |
| headline | 14/20/600 | emphasis |
| body | 14/21/400 | reading text |
| callout | 13/19/400 | secondary |
| subhead | 13/18/500 | labels/buttons |
| caption | 12/16/500 | meta |
| **data** | mono 13/18/450 tnum | facts, ids, amounts, trace |
| eyebrow | mono 11 upper +0.08em | section eyebrows |

## Motion system (fires once, on real state changes; reduced-motion → opacity only)

| journey | moments |
|---|---|
| Upload | drag-over tint+1.005 scale (140ms) · card `.animate-materialize` spring (260ms) |
| Processing | segment fill per stage · `.animate-seg-shimmer` on active · `.animate-seg-pop` on complete · label crossfade · `.animate-draw-check` on Filed (320ms) |
| Archive | rows `.animate-rise-in` w/ 40ms stagger · hover tint 120ms |
| Chat | trace steps `.animate-trace-in` stagger · citation chips scale-in · provenance `.animate-source-sweep` 240ms wash |
| Review | confirm fly-out spring · next card `.animate-review-in` |
| Global | route fades · dialogs scale 0.97→1 · `.animate-skeleton` shimmer |

## Screens — v2 state

Built on the v2 foundation: **shell** (hairline top bar + wordmark, blue-wash active nav, neutral account switcher), **upload** (dropzone + segmented pipeline cards + dock), **archive** (reworked, below). Remaining screens inherit the tokens but await their structural rework:

- **Archive (REWORKED ✅):** a **dense sortable table** is the primary view — columns: document (first-page thumbnail via `GET /documents/{id}/pages/1?dpi=72`, blob-fetched through the auth seam and session-cached; docx/415 → neutral glyph), folder (the new `DocumentOut.primary_class`, batch-loaded server-side), status (live PipelineFill while processing), size, date (mono data voice). Client-side sort over the loaded pages (server keyset order = date-desc default) + an instant search box (title/filename/folder) on top of the server folder/status filters. Folders are demoted to a **filter-chip row** (smart chips → parent chips; selecting a parent reveals its subclass chips; folder create/rename/delete live on the chips). Gallery (cards) one toggle away. Rows `.animate-rise-in`, 40ms stagger capped at 12 rows. **Refiling is a per-row "Move to folder…" menu (`set_primary`) — drag-to-folder was consciously retired** (dnd fights a sortable table, chips are poor drop targets once scrolled, and the menu works on touch). Below `sm` the table collapses to a compact thumb+title list.
- **Chat (RESTYLED ✅):** user turns are accent-fill bubbles (`bg-accent text-on-accent`); the trace collapses to one quiet mono line ("✓ searched your archive · 3 sources · 1.8s" — scope label swaps in for document-scoped chats) that re-opens to the stepped view; citation chips are mono pills with an amber MapPin that materialize in; the rating row reads "Helpful?" → "Thanks". Provenance clicks land on the document view where SourceGlow washes the exact bbox (`.animate-source-sweep`, settles) or flashes the page once when no bbox (`.animate-source-flash`, fades out). ⚠️ Learned here: **Tailwind can't variant custom `@layer components` classes** — `motion-safe:animate-source-*` silently compiled to nothing (the "wash" was a static overlay). Use the bare `animate-*` classes; the global `prefers-reduced-motion` block already collapses them.
- **Review / Document view (RE-SKINNED ✅):** behavior untouched (keyboard 1/2/3 · / · → labelling, candidate chips w/ confidence bars, type-ahead picker w/ inline create, split source ⇄ card, provenance jumps, SourceGlow). Changes: the category-tint dots are gone everywhere (CandidateChip, ClassPicker — now a neutral folder glyph, ClassChip), parent-context labels moved to the mono data voice, and the review card gained a first-page `PageThumb` (links to the document view). `tintForSlug` now has one remaining caller (analytics BarList) and dies with the analytics re-skin.
- **Analytics / Billing (RE-SKINNED ✅):** behavior + dataviz structure unchanged (single-accent series validated on both v2 surfaces — `#2563EB` passes all six checks light and dark; crosshair/keyboard/table twins intact). Changes: BarList identity dots removed (label alone carries identity — `tintForSlug` is deleted), and the **amber purge**: everything warn-flavored that wore `--hl*` now wears the semantic warn ramp — UsageMeter warn state, StatusBadge warn tone, the document-view review banner, the checkout "Test mode" pill (the EmptyState "coming later" pill went neutral). New token **`--warn-text`** (#B45309 light · #F5A623 dark) for warn used as text, since raw `--warn` fails AA at caption size. `--hl*` now appears only in: wordmark, citation pills, SourceGlow.
- **Mobile (DONE ✅):** below `lg` the drawer is gone — a fixed **bottom tab bar** (Upload / Archive / Ask / **More**) with a warn dot + badge when documents await review; the More sheet holds Review/Analytics/Billing plus the account bits (backend status + switcher; the switcher also stays in the top bar). New **`Sheet`** primitive (`ui/sheet.tsx`: scrim, `.animate-sheet-up` 240ms, safe-area padding, Escape/scrim dismiss, scroll lock, focus lands on close). The **chat rail** and the **document source pane** open as sheets on narrow screens (source renders exactly once via the `useMedia` hook — desktop grid *or* mobile sheet; provenance jumps and citation arrivals auto-open it). ProcessingDock sits above the bar. Touch ≥44px on chips, move menus, pagers, rating, trace toggle, segmented controls (desktop keeps the compact sizes via `sm:`).

The approved visual direction (palette, components, live motion demos, light+dark) is the rev-2 preview artifact: `https://claude.ai/code/artifact/31006d72-d337-4ec8-b0c5-b1d213b4761b`.

## Quality floor

Responsive to 375px with no horizontal scroll; touch ≥44px; visible keyboard focus; AA contrast in both themes; color never the sole signal; real empty/loading/error states (direction, not mood); every value traces to a token.
