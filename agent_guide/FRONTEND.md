# FRONTEND.md — filemindr

Machine-readable design tokens + component/screen specs. The contract between `FileMindr_Design_System.pdf` and the code. Edit token values here; agents read this, not the PDF.

Aesthetic in one line: **warm-paper Apple calm, provenance as identity.** Barely-warm paper neutrals; one ink accent (fountain-pen indigo) for interaction; one **reserved bold — highlighter amber — used *only* where the machine shows what it read and where** (citations, source glow, the read-through). Two type families, three weights, calm spring motion.

**Identity: "Ink & Manila" (implemented in `web/`).** The earlier build read as too monochrome, so the paper-and-ink soul is now anchored by three moves (validated with the `ui-ux-pro-max` skill): (1) a **deep fountain-pen-ink masthead** (`--ink`→`--ink-2` gradient, cream `--on-ink` serif wordmark) as the app's identity band; (2) a **category color system** — each top-level class owns a warm, earthy folder color (`tintForSlug`, intentional hues for known parents + a hashed earthy palette otherwise) used on folder dots, card tabs, and list icons, *always* beside the folder name so color is never the sole signal; (3) **warm manila filing cards** (`--card`) with a bold category tab and a **serif "record" title**, over a subtle **paper-grain** canvas. Everything still resolves to tokens; the highlighter stays the one reserved provenance color.

## Design direction (skills pass — `frontend-design` + `ui-ux-pro-max`)
Grounded in the subject: an **intelligent personal archivist**. Its world is paper, ink, filing tabs, and a human's highlighter marking *exactly where a fact lives*. The product's soul is **provenance** (page + bbox), so the identity is built on it rather than on a generic app chrome.

**The one aesthetic risk (the signature):** provenance is made physical. A citation is a highlighter mark; clicking it **sweeps a highlighter stroke over the exact source region** on the page. That same highlighter language is the app's only bold color and its only bold motion — everything else stays quiet paper-and-ink. Supporting (quiet) motif: DocumentCards read as **filing cards** with a class **tab**, giving the archive its texture without shouting.

**Defaults deliberately rejected** (and what we do instead):
- *SaaS iris/blue* (`#3D63DD`, the prior file's pick) → **desaturated fountain-pen indigo** `#3B5488`; the only saturated color is the highlighter, and it always *means provenance*.
- *Inter as the whole personality* (the reach-for-anything default) → personality is carried by an **Instrument Serif** display ("elegant reading room" — a high-contrast serif for titles) + **Geist Mono** (machine/data voice); Inter is kept only as the neutral body/UI workhorse *under* them. **Guard against the cream-serif cliché:** the serif is **display-only** (body is Inter), the surface is barely-warm paper (not cream), and the palette is ink+highlighter (not terracotta) — so it reads as a *reading room*, not luxury-generic.
- *Cool Apple gray* (`#F5F5F7`) → **barely-warm paper** `#F7F5F1` (Apple *Books/Notes* register, not cold dashboard) — kept subtle.
- Also avoided: near-black+acid, and broadsheet hairlines/zero-radius — we keep soft radii + gentle depth.

## Stack
Next.js + TypeScript · Tailwind (tokens as CSS vars) · Radix UI (a11y primitives) · Framer Motion (the 3 signature motions) · dnd-kit (archive drag-drop, review deck) · react-pdf/pdf.js (source render + bbox provenance) · Recharts/Visx (analytics) · TanStack Query (server state). Fonts via `next/font`: **Instrument Serif** (display/titles ≥22px; 400 + italic only) + **Inter** (body/UI) + **Geist Mono** (data); SF Pro / SF Mono on Apple platforms.

**Architecture (locked):** the web app is a **pure thin client** over the backend's JSON + SSE API (bearer = user UUID + `X-Account-Id`). **No business logic in the web tier** — anything derived (conversation titles, grouped citations, processing-step labels, add-vs-replace class semantics) is computed server-side so the **same API serves a future React Native app** with zero re-implementation. Backend enables **CORS** (web browser + native both call it directly); Next.js `rewrites` are dev convenience only, never a correctness dependency. Backend and frontend stay in separate trees (`web/`), deployable independently.

## Design tokens — CSS variables

```css
:root {
  /* accent — fountain-pen ink (calm authority; deliberately NOT SaaS blue) */
  --accent-50:#EEF1F7; --accent-100:#DCE3F0; --accent-300:#9DB0D2;
  --accent:#3B5488; --accent-hover:#314670; --accent-active:#283959;
  --on-accent:#FFFFFF; /* text/icons ON an accent fill; flips with the accent's lightness */

  /* ink — the masthead identity band (deep desaturated indigo, "pen on page") */
  --ink:#202A44; --ink-2:#171F34;
  --on-ink:#F3EFE8; --on-ink-muted:#A6AFC7; --on-ink-border:rgba(243,239,232,.14);

  /* highlighter — the ONE bold color, RESERVED for provenance / "the machine read this".
     Never body text, never the sole signal: used as a mark/wash behind dark ink, a pill, a dot. */
  --hl:#E0930B; --hl-strong:#B9740A; --hl-wash:rgba(255,206,80,.35);

  /* paper — barely-warm neutral ramp (canvas is warm, not cream) */
  --p-0:#FFFFFF; --p-50:#F7F5F1; --p-100:#F0ECE4; --p-200:#E4DFD5;
  --p-300:#CFC8BA; --p-400:#A69E8F; --p-500:#7A7266; --p-600:#585349;
  --p-700:#3E3931; --p-900:#1C1A16; --p-950:#100F0C;

  /* semantic (light) */
  --canvas:var(--p-50); --surface:var(--p-0); --surface-2:var(--p-100);
  --card:#FDFBF6; /* warm manila filing card */
  --border:var(--p-200); --border-strong:var(--p-300);
  --text-1:var(--p-900); --text-2:var(--p-600); --text-3:var(--p-500);

  /* status (warm-leaning to sit in the paper world) */
  --ok:#2F855A; --warn:var(--hl); --danger:#C0392B; --idle:var(--p-500); --info:var(--accent);

  /* radius */
  --r-sm:8px; --r-md:12px; --r-lg:16px; --r-xl:22px; --r-pill:999px;

  /* elevation */
  --e1:0 1px 2px rgba(20,23,28,.06), 0 1px 1px rgba(20,23,28,.04);
  --e2:0 4px 12px rgba(20,23,28,.08), 0 2px 4px rgba(20,23,28,.05);
  --e3:0 16px 48px rgba(20,23,28,.16);

  /* motion */
  --ease-quiet:cubic-bezier(.32,.72,0,1);
  --ease-standard:cubic-bezier(.4,0,.2,1);
  --dur-micro:160ms; --dur-base:220ms; --dur-emphasis:320ms; --dur-sheet:420ms;
}

:root[data-theme="dark"] {
  /* warm dark (roasted paper, not pure black) */
  --canvas:#14120F; --surface:#1E1B17; --surface-2:#26221C; --card:#211D18;
  --ink:#10141F; --ink-2:#0A0D15; --on-ink:#E9E6DF; --on-ink-muted:#8B93A9;
  --border:#332E27; --border-strong:#463F35;
  --text-1:#F3EFE8; --text-2:#B8B0A2; --text-3:#8A8275;
  --accent:#8AA0D8; --accent-hover:#A2B4E4; --accent-active:#BDCAEC;
  --on-accent:#10141F; /* dark accent is light → dark ink on it keeps AA */
  --hl:#F0B23D; --hl-strong:#FFC661; --hl-wash:rgba(240,178,61,.24);
  --ok:#48BB78; --warn:var(--hl); --danger:#F16A5D; --idle:#8A8275;
  /* dark lifts via surface + border; --e3 only for modals */
}
```

## Type scale
| Token | family | size/line | weight | tracking | use |
|---|---|---|---|---|---|
| display | Instrument Serif | 40/46 | 400 | -0.01em | page titles, hero, doc titles |
| title1 | Instrument Serif | 30/36 | 400 | -0.01em | section heads |
| title2 | Instrument Serif | 22/28 | 400 | 0 | sub-sections |
| title3 | Inter | 18/24 | 600 | -0.01em | card titles |
| headline | Inter | 16/22 | 600 | 0 | emphasis |
| body | Inter | 15/23 | 400 | 0 | reading text |
| callout | Inter | 14/20 | 400 | 0 | secondary text |
| subhead | Inter | 13/18 | 500 | 0 | labels |
| caption | Inter | 11/14 | 500 | 0.01em | meta, badges |
| **mono-data** | Geist Mono | 13/18 | 450 | 0 | **facts, IDs, amounts, dates, trace** |

**Family rule:** display/title1/title2 (≥22px "editorial" sizes) = **Instrument Serif**; title3 and everything ≤18px UI/body = **Inter**; data = **Geist Mono**. **Instrument Serif ships regular + italic only** — hierarchy among the serif sizes comes from **size + the face's high contrast, not weight** (no serif bold; use *italic* for editorial emphasis). Never set the serif below ~20px (high-contrast serifs get fragile small).

Spacing: 4pt grid — `2 4 8 12 16 20 24 32 40 48 64 80`. Weights: Inter 400/500/600 · Instrument Serif 400 + italic · Geist Mono 450.

## Signature motions (Framer Motion)
1. **Pipeline fill** — upload card stage pips advance `received→ocr_done→extracted→indexed`; active stage pulses 1.2s. Bind to real backend status.
2. **Trace reveal** — retrieval steps stream in, 120ms stagger, fade+rise 8px.
3. **Highlighter provenance (the signature)** — the identity motion. Hover a citation → source region gets a **highlighter wash** (`--hl-wash`) swept in over ~160ms; click → smooth-scroll to the page and a ~600ms **swept highlight** over the exact bbox (left→right, like a marker stroke), settling to a resting tint. The same marker language flashes once over key regions as the machine "reads" a doc during processing. This is the only place the highlighter color and a bold motion appear.

All motion: honor `prefers-reduced-motion` → opacity-only fades, no sweep/transform.

## Components (token-driven; no inline colors/radii/durations)
Actions: Button (primary/secondary/ghost/destructive), IconButton, SegmentedControl, CommandPalette (⌘K).
Inputs: TextField, Search, Dropzone, Select/Combobox, Toggle, Slider, ChipInput (classes).
Containers: Card, DocumentCard (**filing-card treatment: warm surface + a class "tab"; quiet, not decorative**), SidePanel, Modal, BottomSheet, Tabs, Accordion (trace), Table.
Signals: StatusBadge, ConfidenceBar, ClassChip, CitationPill, Toast, Tooltip, Skeleton, EmptyState.
Nav: Sidebar, TopBar, Breadcrumb, AccountSwitcher (personal ⇄ company).
Data: StatTile, Line/Area/Bar chart, Sparkline, UsageMeter, PricingCard.
Phase-6 additions: FolderTree (taxonomy parent▸child + smart folders), DraggableDocCard + DropFolder (dnd-kit), ProcessingDock (persistent background-status pill), ReviewDeck + CandidateChip, ConversationList, SourcePane (pdf.js page + bbox highlight), SourceGlow.

## Screens → key components & behavior

### Upload  (`/`)
Dropzone (any file) → optimistic DocumentCard in `received`, animates via Pipeline fill. Multi-file, paste, browse all funnel to one flow; duplicates recognized. Copy is user-side ("Drop files here", "12 indexed").

**Never-wait model:** upload/processing are fully backgrounded — the user can navigate, open the archive, or chat with already-indexed docs while new ones process. Optimistic cards land immediately; TanStack Query **polls `GET /documents` (~1s while any doc is non-terminal, stops when all terminal)** and drives Pipeline fill from the real `status` enum. Stage copy: received→"Reading" · ocr_done→"Understanding" · extracted→"Filing" · indexed→"Filed" (or needs_review→amber "Review"). A **ProcessingDock** (persistent bottom-right pill, glass) shows "⟳ N processing" on every screen; expands to per-doc stages. `needs_review` docs badge the Review nav.

### Archive  (`/archive/{slug?}`)
Finder-style. **FolderTree** rail from `GET /classes` (`parent_id`/`parent_slug`/`document_count`): parent classes = folders, subclasses = subfolders, file-type color-tint per parent, spring expand/collapse. Smart folders pinned: Inbox (recent) · Needs review (badge) · Unfiled (no class) · All. Main = `GET /documents?class={slug}` (**subclass-aware** — a parent lists its children's docs), views: Gallery / List / Columns.
**Drag-drop refile (dnd-kit):** drag DocumentCard(s) onto a folder → folder lights iris, card lifts (e2→e3), count animates. Default = **add label**; context-menu **Move here** = replace. Both call `POST /documents/{id}/classes` — *server owns add-vs-replace* (see backend gaps), so native reuses it. Create/rename/delete custom folders via `POST`/`DELETE /classes`; system folders show a lock (409-immutable). **Folders are labels, not a filesystem** — a doc can appear in several; the UI is honest about this (a card can live in multiple folders).

### Review  (`/review`)  — human-in-the-loop class labelling
The `needs_review` queue as a fast, keyboard-driven **ReviewDeck** (one doc at a time, Superhuman-speed × Apple-calm), tailored to `documents.review_reason`:
- **ambiguous** → the 2–3 candidate **CandidateChips** with ConfidenceBar side-by-side; confirm by tap / drag-doc-onto / keys `1`·`2`·`3`; `→` skips.
- **low_confidence / no_class** → type-ahead class picker over the taxonomy + **create-folder inline**, with summary + source thumbnail to decide.
On confirm → card flies into its folder (shared-layout spring) + check, next advances, progress pill "2 of 3", **undo toast**. Finish = "All filed. Inbox zero." (one restrained beat, no confetti). Writes `POST /documents/{id}/classes` (`assigned_by=user`) → clears flag, advances to `indexed`. Reversible; never nags.

### Document view  (`/documents/{id}`)
Split: source render (left) ⇄ card (right). Card = title, summary, ClassChips + ConfidenceBar, **typed facts in mono with `↩` provenance jump (signature)**, entities (people/orgs/places), dates-with-roles, "N facts indexed" (the glimpse, no vectors exposed). `+ add class` creates/labels user classes. Empty class set is a calm valid state.

### Ask  (`/chat/{id?}`)
**ConversationList** rail (`GET /conversations` — see backend gaps) → **continue any chat** by loading `GET /conversations/{id}/messages`; "it"-style follow-ups already work (backend memory). New turn → `POST …/messages/stream` (SSE). Render events `intent → find_documents/searching → escalating → done` as the collapsible **trace** (Trace reveal motion, mono) in plain language — *including which doc/class is being searched* (the "what's being fetched from where" experience) and an honest "Thinking harder…" on GPT-4o escalation; collapses to "Worked for Ns" after `done`. Streamed answer token-by-token; **citations grouped by document** (server-grouped) as CitationPills (click-to-source → SourceGlow). Numeric answers from typed facts — trace says so. Scope toggle: whole archive / this document. "Unsupported" honesty path. Rating row under each answer (control shown; learning loop deferred).

### Ratings
Thumb up/down (1 tap) + optional 1–5 stars. Low rating opens diagnostic reasons: `not grounded · missing document · wrong number · wrong document` + note. Writes to the answer's retrieval trace → feeds analytics + eval.

### Analytics  (`/analytics`)
Two lenses. **Usage:** documents over time, queries/day, storage, top classes, token spend, most-asked docs. **Quality:** answer rating %, grounded %, retrieval latency, extraction success. All derived from `processing_events` + `retrieval_traces` + usage events. Sparse charts, neutral ink, single accent series.

### Billing  (`/billing`)
Plan card + UsageMeters (documents / queries / storage) using status palette (amber→red near limit). PricingCards (Free/Pro/Team) mapped to real cost drivers. Invoices + payment management. Team tier unlocks shared company accounts + audit.

## Backend gaps for Phase 6 (do these server-side — native reuses them)
Per the locked architecture, each is API-side so web + React Native share one implementation. Add via new Alembic migrations where schema changes (additive; ask before destructive).
1. **`GET /conversations`** — list w/ `title`, last-message preview, `updated_at` (chat rail, continue-any-chat). Needs a conversation **`title`** (store; derive from first user message or a cheap generation) — *not* a client-side hack.
2. **File / page-image endpoint** — `GET /documents/{id}/file` and per-page render (thumbnails + **bbox provenance**; bboxes already in `ocr_cache`). Enables Citation glow / SourceGlow; without it, citations degrade to page-number only.
3. **`DELETE /documents/{id}`** — archive trash (+ storage cleanup).
4. **Add-vs-replace on `POST /documents/{id}/classes`** — support `mode=add|replace` (drag-to-folder = add, review/move = replace) so the semantics live server-side, not in each client.
5. **Grouped citations** in the chat/answer payload (group facts by document) — server-side so native doesn't regroup.
6. **CORS** middleware (web browser + native direct calls). *(No new SSE needed — status polling covers Pipeline fill in v1; a per-doc `processing_events` SSE is a later nicety.)*

Sequencing: gaps **1–2** land right before the Ask + provenance milestones; **3–5** with archive/refile polish. Web-only build order: shell → archive → upload/never-wait (zero backend changes) → then the above.

## Quality floor
Responsive to mobile; touch ≥44px; visible keyboard focus; AA contrast; color never the sole signal; real empty/loading/error states (direction, not mood). Every value traces to a token.
