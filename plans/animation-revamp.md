# Animation Revamp — plan & status

Motion pass for the Filemindr Cloud web app, following Emil Kowalski's design-engineering
methodology (skills: `emil-design-eng`, `find-animation-opportunities`, `improve-animations`).

**Motion dial: low–moderate.** This is a crisp professional archivist/dashboard — feedback
over flourish, crisp and fast, delight reserved for rare states. Restraint is the point.

## Recon (as of this pass)

- Stack: Next 16 + Tailwind v4, **pure-CSS motion, no animation library**.
- Existing system (`web/src/app/globals.css`): 11 fire-once `@keyframes`, a good token set
  (`--ease-quiet` = the Ionic drawer curve; `--dur-micro/base/emphasis/sheet`), a proper
  `prefers-reduced-motion` block, `:focus-visible` everywhere.
- Signature moments already curated: pipeline fill, trace reveal, SourceGlow, drawn check,
  materialize, sheet-up, review-in. The app is **not** flat.
- Real gaps: **0 `:active` press states** app-wide; menus/popovers have **no
  transform-origin awareness**; sheet/toast/menus **pop out** (no exit); `--ease-standard`
  is the weak Material curve; hover states aren't `(hover:hover)`-gated.

---

## Part 0 — Foundation  ·  STATUS: ✅ DONE

Added to `globals.css` `:root` and `@layer components`; new hook `web/src/lib/use-presence.ts`.

| Token / class | Value | Purpose |
| --- | --- | --- |
| `--ease-out` | `cubic-bezier(0.23, 1, 0.32, 1)` | Emil's strong entrance/feedback curve (was missing) |
| `--dur-press` | `140ms` | press-feedback standard |
| `.pressable` | `transition: transform var(--dur-press) var(--ease-out)` + `:active { transform: scale(0.97) }` | universal press feedback |
| `@keyframes pop-in` + `.animate-pop-in` | `opacity:0; scale(0.97)` → settled, `150ms --ease-out` | origin-aware menu/popover entrance |
| `@keyframes pop-out` + `.animate-pop-out` | reverse, faster | menu/overlay exit |
| `@keyframes fade-in` / `fade-out` | opacity only | scrims |
| `@keyframes sheet-down` | `translateY(24px)` + fade, faster than `sheet-up` | sheet exit |
| `@keyframes toast-in` / `toast-out` | `translateY(8px)` + fade | toast enter/exit (symmetric) |

Keep `--ease-quiet` (sheets/drawers), `--ease-spring` (materialize/seg-pop delight). New hook
`web/src/lib/use-presence.ts` keeps overlays mounted through their exit animation.

---

## Part 1 — Audit fixes  ·  STATUS: ✅ DONE (except #5, deferred)

| # | Sev | Location | Fix | STATUS |
| --- | --- | --- | --- | --- |
| 1 | HIGH | all primary filled CTAs + chrome icon buttons + overlay controls | `.pressable` (`scale(0.97)`, 140ms ease-out) applied. Nav items (sidebar/tab-bar) deliberately excluded — high-frequency navigation, restraint. | ✅ |
| 2 | MED | `shell/user-menu`, `archive/move-menu` | origin-aware `.animate-pop-in` from trigger corner (`origin-top-right`). `account-switcher` is a native `<select>` → left alone (OS renders its menu). | ✅ |
| 3 | MED | `ui/toast`, `ui/sheet`, both menus | enter+exit via `usePresence`; exit faster than enter (sheet 180ms, toast 160ms, menus 120ms) | ✅ |
| 4 | MED | feedback/menus | now use `--ease-out` (the new strong curve); `--ease-quiet` kept for sheets | ✅ |
| 5 | LOW | ungated `transition-colors` hovers | gate behind `@media (hover:hover) and (pointer:fine)` | ☐ deferred (low value; `transition-colors` implies no motion, so touch false-positives are cosmetic only) |

**Verified:** `tsc --noEmit` clean · `eslint` clean · dev server compiles clean · authenticated playwright smoke (chat + user-menu pop-in + archive) = **0 console errors**, overlays render correctly.

---

## Part 2 — Opportunities  ·  DEFERRED (gated, optional delight)

| # | Location | Motion | Purpose | Freq |
| --- | --- | --- | --- | --- |
| 1 | `ask/message-thread` new answer | `@starting-style` fade+rise | prevent jarring change | occasional |
| 2 | `archive/document-table`, `ask/conversation-list` first paint | `.animate-rise-in` + 40ms stagger, cap ~8 | prevent jarring change | occasional |
| 3 | empty states (chat/archive/review-done) | one `materialize` + staggered content | delight (rare tier) | rare |
| 4 | trace expand, filter-chips subclasses | height+opacity `200ms ease-out` | state indication | occasional |
| 5 | destructive deletes | optional hold-to-confirm `clip-path` fill | feedback / slip-prevention | occasional |

## Rejected (deliberately NOT animated — restraint)

- `shell/command-palette` ⌘K — keyboard-initiated, 100+/day. Never animate. (Already correct.)
- Sidebar nav / tab-bar route switches — core navigation, high-frequency. Instant.
- `viz/*` analytics charts — functional data the user reads; motion hinders.
- Theme toggle — instant; a theme-flip animation is frequent and nauseating.
