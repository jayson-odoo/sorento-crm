# Design language reference

The one-page reference to read before touching any UI file. Promotes section 3 of
`documentation/plans/design-system/PLAN-apple-alignment.md` into a durable home now that
Apple Alignment has largely shipped (S1-S6b). Terse reference prose and tables, not an essay.

## 1. Precedence

Order on conflict, strongest first:

1. `PRINCIPLES.md`
2. `documentation/reference/ADR-PRODUCT-STANDARDS.md`
3. This file
4. Any installed external design skill (`.agents/skills/emil-design-eng`, `apple-design`,
   `animate`, `review-animations`, `find-animation-opportunities`, `prototype`,
   `pick-ui-library`)

An external skill may PROPOSE a change to this file via an ADR in `documentation/adr/`; it
never overrides it inside a PR.

## 2. Tokens (`sorento_crm_frontend/css/config.reui.css`)

| Group | Token | Value |
| --- | --- | --- |
| Motion | `--ease-standard` | `cubic-bezier(0.2, 0, 0, 1)` |
| Motion | `--duration-fast` | `150ms` |
| Motion | `--duration-base` | `200ms` |
| Motion | `--duration-slow` | `300ms` |
| Materials | `--material-regular` | `color-mix(in oklab, var(--background) 72%, transparent)` (header) |
| Materials | `--material-thick` | `color-mix(in oklab, var(--background) 88%, transparent)` (sidebar) |
| Materials | `--material-blur` | `24px` |
| Materials | `--material-edge` | `color-mix(in oklab, var(--foreground) 8%, transparent)` |
| Materials | `--scrim` | `color-mix(in oklab, black 50%, transparent)` (lightbox backdrop; the reduced-transparency block raises it to 72% and drops the blur) |
| Z-scale | `--z-header` | `10` |
| Z-scale | `--z-sidebar` | `20` |
| Z-scale | `--z-banner` | `30` |
| Z-scale | `--z-modal` | `50` |
| Radius | `--radius` | `0.5rem` (base); `--radius-sm/-md/-lg/-xl` derive from it |
| Type | `--font-sans` | Inter via `--font-inter`, `ui-sans-serif, system-ui, sans-serif` |
| Type | `--text-2xs` / `--text-2sm` | `0.6875rem` / `0.8125rem`, each with a baked line-height |
| Type | tracking | `lg`/`xl`/`2xl` tighten (`-0.01em` to `-0.02em`); `xs`/`2xs` open up (`0.01em`/`0.02em`) - large text tightens, small text opens, so a heading never needs a hand-tuned `tracking-tight` beside it |

Rule (the file's own comment style): no raw `cubic-bezier(...)`, no `duration-[N]`, no
`z-[N]`, no `text-[Npx]` in feature code. A new step is added only when a real consumer
arrives - see the file's own "Materials" comment for the precedent.

## 3. Motion (`sorento_crm_frontend/lib/motion.ts`)

- `SURFACE_SPRING`: `{ type: 'spring', bounce: 0, visualDuration: 0.3 }`. Critically damped
  (`bounce: 0`) because these are not driven by a flick or drag; `visualDuration` is tuned to
  `--duration-slow` so a JS spring and a CSS transition read at the same pace. A spring
  re-targets from wherever the value currently sits, so re-opening a surface mid-close
  continues live instead of jumping back to 0 (interruptible).
- `REDUCED_MOTION_TRANSITION`: `{ duration: 0.01 }` - a same-frame opacity change, no scale,
  no travel, no overshoot.
- `surfaceTransition(prefersReducedMotion)`: picks between the two above.
- `surfaceVariants(prefersReducedMotion)`: fade + scale 0.96 -> 1 in (never scale 0); reduced
  motion drops the scale and keeps only the fade.
- `useOpenState()`: mirrors a Radix root's open state into plain React state so a sibling
  `Content` can gate an `<AnimatePresence>` - Radix's own Presence unmounts on a CSS animation
  it can detect, which a JS spring is not.
- Origin anchoring: the inner `motion.div` uses
  `origin-(--radix-popper-content-transform-origin)` (Radix sets it to the trigger side) or a
  fixed `origin-*` utility for a surface with no Radix popper. Modals stay centered.

### Rulings (2 Sep 2026)

| Topic | Ruling |
| --- | --- |
| Easing curve | `--ease-standard` stays. It is already a custom curve; do not introduce a second one. A stronger ease-out is an ADR, not a PR. |
| Duration per surface | Lightboxes (Dialog, Sheet, AlertDialog) = `--duration-slow` 300ms. Menus and popovers (DropdownMenu, Popover, Select, Tooltip) = `--duration-base` 200ms. Pressed feedback = `--duration-fast` 150ms. `lib/motion.ts` currently runs one 300ms spring for all surfaces; the 200ms menu preset is follow-up work, not part of this docs slice. |
| Frequency gate | Adopt the emil-design-eng frequency table verbatim: 100+ times/day (keyboard shortcuts, command palette toggle) = no animation; tens/day (hover, list navigation, row expand/collapse, tab switch) = none or `--duration-fast` opacity only; occasional (lightboxes, toasts, drawers) = standard surface spring; rare (onboarding, celebration) = may add delight. Keyboard-initiated actions never animate. |

### Hard-fails in review

- `transition-all` or `transition: all`
- `transform: scale(0)` as an entrance
- `ease-in` on any entrance
- a raw `cubic-bezier` outside `config.reui.css`
- motion on a keyboard-initiated action
- a new animation with no `prefers-reduced-motion` handling (use `useReducedMotion` from
  `lib/motion.ts`)

## 4. Primitives roster

| Component | File | When to use |
| --- | --- | --- |
| `PageHeader` | `components/common/PageHeader.tsx` | Every page title + breadcrumb; crumbs derive from `MENU_SIDEBAR` unless overridden |
| `DetailActions` + `ListPager` | `components/common/DetailActions.tsx`, `components/common/ListPager.tsx` | Record card: pager, gear LEFT of the single primary button, Delete last in the gear |
| `DataGrid` / `DataGridTable` | `components/ui/data-grid.tsx`, `components/ui/data-grid-table.tsx` | EVERY tabular list; `tableLayout: { width: 'fixed', columnsResizable: true }`, explicit `size`, `truncate` + `title`; a deliberately pinned column keeps its pinned styles on a phone, nothing pins automatically |
| `Badge` pill | `components/ui/badge.tsx` | Status = rounded tinted pill with a dot (`status` prop, resolves via `getStatusBadgeVariant`) |
| `Tabs` with `TabsList variant="line"` | `components/ui/tabs.tsx` | Form/detail tabs (the default); pills (`variant="default"`) only for a two/three-option segmented switch inside a dialog |
| `Dialog` / `Sheet` / `AlertDialog` | `components/ui/dialog.tsx`, `components/ui/sheet.tsx`, `components/ui/alert-dialog.tsx` | Lightbox surfaces, `modal ?? true`, shared `OVERLAY_CLASS` / `OVERLAY_CLASS_STATIC` from `components/ui/primitive-classes.ts` |
| `SearchableSelect` / `SearchableMultiSelect` | `components/common/SearchableSelect.tsx`, `components/common/SearchableMultiSelect.tsx` | Every dropdown-select; optional ones set `clearable` |
| `ListSearchInput` | `components/common/ListSearchInput.tsx` | Every list search box |
| `FileDropzone` | `components/common/FileDropzone.tsx` | File upload surfaces |
| `DeferredActionButton` / `useDeferredAction` | `components/common/DeferredActionButton.tsx`, `hooks/useDeferredAction.tsx` (list rows: `hooks/useDeferredRowAction.tsx`, `components/common/deferredToast.tsx`) | Destructive + detach actions (delete, archive-as-delete, unlink) - see ADR section 2. `ConfirmDeleteDialog` (`components/common/ConfirmDeleteDialog.tsx`) is retired; a new importer of it, or of a destructive `AlertDialog`, is a defect outside the named carve-outs |
| `sonner` toast | `lib/toast.ts` for EVERY call site (`success`/`error` default duration + close button per M6-04; import `toast` from here, never `'sonner'` directly); `components/ui/sonner.tsx` + `ClientProviders.tsx` mount the one `<Toaster>` and are the only files allowed to import `sonner` itself | Success/error feedback, deferred-action toasts on list rows |

Pressed + touch: `PRESSED_CLASS` and `COARSE_HIT_TARGET_CLASS` from
`components/ui/primitive-classes.ts` on every pressable. Button sizes do not change - the
coarse-pointer `::after` hit area supplies the 44px target invisibly.

## 5. Surviving decisions (apple-alignment plan)

- **D4** - pager is page-scoped and client-side: it reuses the rows the list page already has
  in the React Query cache, `"n / pageSize"`, next on the last row fetches the following page.
- **D6** - detail record card actions, left to right: pager, gear (secondary actions,
  separator, Delete in red last), one primary button. Wraps under the identity at 375px.
- **D7 / D16** - no confirm dialogs for a destructive or detach action; it is a server-deferred
  pending action instead (10s window for hard delete, 5s for reversible, both configurable in
  System Settings). Escape does not cancel it; closing the tab still commits.
- **D11** - sidebar keeps the GRN / SPO abbreviations; page titles (not the sidebar) expand
  them. SPO never becomes "Supplier PO" in the sidebar.
- **D12** - Inter stays as `--font-sans`.
- **D13** - `vaul` for the mobile nav drawer and bottom sheets; desktop side sheets stay Radix.
- **D15** - one `recordActions` set per entity (`use<Entity>Actions(record)`), shared by the
  list row's "..." menu and the record's gear - same items, same order, same permissions. No
  Edit item in the row menu; the row click (list) / primary button (record) is the edit path.
  Reference detail pattern: the Users account page (first case for D15).

## 6. Copy and content

- No feature explanations inside the UI - how-to goes to the Outline user guides / FAQ
  (`PRINCIPLES.md` design mandates).
- No UUIDs in the UI - resolve to human-readable identifiers.
- Datetimes render via `formatDateTimeInMalaysia`, never `formatDateTime(new Date())`.
- Empty value rendering follows `ADR-PRODUCT-STANDARDS.md` section 1e.
- Every detail section renders, including when empty, with an explicit empty state + CTA -
  never hide a section on missing data.

## 7. Responsive

- Usable and non-clipped at 375px AND 1280px.
- DataGrid scrolls sideways inside its own `overflow-x` container, `min-w-0` on the scroller.
- Tab strips scroll, never wrap.
- Toolbars use `flex-wrap`.

## 8. Where the external skills plug in

| `/feature` step | Skill | Mode |
| --- | --- | --- |
| Step 2 grill | `animation-vocabulary` | Naming only |
| Step 3 UAC | `find-animation-opportunities` | Read-only; capped output becomes `[UX]` ACs or an explicit no-motion list |
| Step 6 Phase 1 | `prototype` | Throwaway, before Phase 1 |
| Step 6 Phase 1 | `animate` | Decision gate for any new motion added in Phase 1 |
| Step 8 review | `emil-design-eng` | Before/After/Why table on every UI diff |
| Step 8 review | `review-animations` | Only when the diff touches motion |
| Any new FE dependency | `pick-ui-library` | First - repo picks already made: motion, sonner, vaul, embla-carousel-react, @dnd-kit |
| Periodic | `improve-animations` | - |

Not used here: `animate-expo`, `write-swift`.
