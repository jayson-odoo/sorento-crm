# UAC - Searchable Dropdown Standard

> Independently-verifiable Given/When/Then contract. Phase-2 test report keys back to these ids
> (PASS/FAIL/DEFERRED). No plan ships without this file. Governs: `PRINCIPLES.md` >
> `documentation/reference/ADR-PRODUCT-STANDARDS.md`.

**Slug:** `searchable-dropdown-standard`
**Domain:** design-system
**Type:** FE component standardization + system-wide migration + doctrine
**Status:** DRAFT (grilled, pre-code)

## Problem

Dropdowns in the system are inconsistent. 110 files use the Radix `@/components/ui/select`
(native-style, **not searchable**). A shared `SearchableSelect`/`SearchableMultiSelect` exists but
is nearly unused (2 / 0 usages). 8 bespoke `*Combobox.tsx` each hand-roll their own
Popover+Command picker. Users get a searchable dropdown in some places and a non-searchable one in
others, at random.

## Doctrine (the design principle this establishes)

**Every dropdown-select in the system MUST be searchable, and MUST use the standard component.**
"Dropdown-select" = click a field → a popover opens showing an option set → filter by typing in the
popover's search box → pick one (or many). Search is **always shown**, with **no option-count
threshold** - a 2-option Active/Inactive dropdown is searchable too.

**Out of scope (NOT a dropdown-select, left untouched, NOT banned):** the free-text type-ahead
pattern (`AsyncCombobox` / `AsyncMultiCombobox`) where the user types into the field/textarea itself
and suggestions appear - used by the portal `SubmissionForm`. Different interaction; keeps its own
component.

## Locked decisions (from grill)

| # | Decision |
|---|---|
| D1 | Every dropdown searchable. **No threshold.** Search box always visible, even for 2 options. |
| D2 | **One component, two runtime modes:** static (`options[]`, client filter) OR async (`fetchOptions(q)`, server search). Caller supplies data one way; component branches. |
| D3 | **Two public components** (not a `multiple` flag): `SearchableSelect` (single, `value: string`) + `SearchableMultiSelect` (multi, `value: string[]`). Shared internal skin. Each supports both D2 modes. |
| D4 | Trigger **pixel-matches Radix `SelectTrigger`** - height, border, radius, chevron, focus ring, disabled, placeholder color. Migration = zero visual diff. |
| D5 | Enforcement = **all three**: ESLint `no-restricted-imports` ban on `@/components/ui/select` + raw `<select>` + ad-hoc `CommandInput` outside the standard; `PRINCIPLES.md` hard-fail rule; **delete `ui/select.tsx` after migration completes.** |
| D6 | Migration **staged by domain cluster**, each an independently-reviewable PR. ESLint ban lands day 1 with a **shrinking allowlist** grandfathering the not-yet-migrated files; each PR deletes its entries. Allowlist → 0 = done → delete `ui/select`. |
| D7 | **FE-only scope. Async opt-in per caller.** No mandated server search contract. Migrated Selects default to static client-filter (their data already loads). Async only where list is large AND a search endpoint already exists. Net-new endpoints = tracked follow-up, not a blocker. |
| D8 | **Fold + delete the 8 bespoke popover-pick comboboxes** (Warehouse, Product ×2, PackingList, Supplier, ProductComboboxSearchable, Brand, Category) into the standard, via their domain PRs. `AsyncCombobox`/`AsyncMultiCombobox` untouched. |
| D9 | Async mode: **`selectedOption?: {value,label}` fallback** so the trigger label + checkmark survive when the current value isn't in the fetched page. **Eager first-page fetch on open** (empty query), 300ms debounce on keystroke, stale-drop by last-query guard, min-chars = 0. |
| D10 | Grouping = optional `group?: string` on option → `CommandGroup` headings (covers the 3 grouped Selects). Form wiring = plain `onChange(value)`; **no react-hook-form anywhere** (0 files), no `Controller` adapter. |
| D11 | **`clearable?: boolean`** opt-in (default false; required fields not clearable). When true → explicit × affordance. **Re-click-to-deselect on single-select removed** (surprising). Multi keeps click-toggle. |
| D12 | Component upgraded **in place** (`components/common/SearchableSelect.tsx` + `SearchableMultiSelect.tsx`). Doctrine text in `ADR-PRODUCT-STANDARDS.md` (binding) + `PRINCIPLES.md` hard-fail ref + `CLAUDE.md` FE-layering note. UAC-first three-phase process. |

## Acceptance criteria

### AC1 - Search always present, no threshold
- **Given** a `SearchableSelect` with 2 options ("Active", "Inactive")
- **When** the user clicks the trigger
- **Then** a search input is visible inside the popover, and typing "act" filters to "Active".

### AC2 - Static mode, client filter
- **Given** `options={[...20 items]}` and no `fetchOptions`
- **When** the popover opens and the user types
- **Then** filtering happens client-side against `label`/`searchText`, no network request fires.

### AC3 - Async mode, server search
- **Given** `fetchOptions={fn}` supplied
- **When** the popover opens
- **Then** `fetchOptions('')` fires once (eager first page); typing "abc" fires `fetchOptions('abc')` debounced 300ms; a stale earlier response is dropped; a loading state shows while pending.

### AC4 - Async selected-label survival
- **Given** async mode, a `value` set, `selectedOption={{value, label}}` passed, popover closed
- **When** the field renders (nothing fetched yet)
- **Then** the trigger shows the selected label; on open, the selected item shows a checkmark even if not in the fetched page.

### AC5 - Zero visual diff vs Radix Select
- **Given** a form field previously using `@/components/ui/select`, migrated to `SearchableSelect`
- **When** rendered side-by-side (before/after screenshot)
- **Then** trigger height, border, radius, chevron, focus ring, disabled opacity, and placeholder color are identical.

### AC6 - Multi-select
- **Given** `SearchableMultiSelect` with `value: string[]`
- **When** the user picks 3 options
- **Then** the popover stays open, trigger shows 3 chips, each chip has a remove ×, and `onChange` emits the updated array; picking a selected option again removes it.

### AC7 - Clearable opt-in
- **Given** `clearable` (default false)
- **When** false → no clear affordance and re-clicking the selected item does NOT deselect it (single-select)
- **And** when `clearable` true and a value is set → an × affordance appears and clears to empty.

### AC8 - Grouping
- **Given** options with `group` fields
- **When** the popover opens
- **Then** options render under `CommandGroup` headings by group; search filters across all groups.

### AC9 - States render
- **Given** the standard component
- **Then** `disabled` (non-interactive, dimmed), empty (`emptyMessage`), loading (async pending), and long-label (truncate + title) states all render correctly.

### AC10 - Popover escapes clipping
- **Given** a `SearchableSelect` inside a dialog or an `overflow-x-auto` table cell
- **When** opened
- **Then** the popover is not clipped by the ancestor's overflow (Radix Popover portal).

### AC11 - Keyboard + a11y
- **Given** the popover open
- **When** the user presses ArrowDown/ArrowUp/Enter/Escape
- **Then** navigation, selection, and dismissal work; the trigger is a `role="combobox"` button with `aria-expanded`.

### AC12 - ESLint ban active with shrinking allowlist
- **Given** the ESLint `no-restricted-imports` rule for `@/components/ui/select` (+ raw `<select>`, ad-hoc `CommandInput`)
- **When** a new file imports `@/components/ui/select` and is not in the allowlist
- **Then** `npm run lint` errors, message pointing to `SearchableSelect` + the doctrine doc.

### AC13 - Migration completeness
- **Given** all domain migration PRs merged
- **When** the allowlist is inspected
- **Then** it is empty, `@/components/ui/select` has zero remaining importers, the 8 bespoke comboboxes are deleted, and `ui/select.tsx` is removed. Grep for `@/components/ui/select` = 0 hits (excluding the deleted file).

### AC14 - Doctrine recorded
- **Given** the standardization is doctrine
- **Then** `ADR-PRODUCT-STANDARDS.md` states "all dropdowns = `SearchableSelect`/`SearchableMultiSelect`, always searchable"; `PRINCIPLES.md` hard-fail list references it; `CLAUDE.md` FE-layering section notes it.

### AC15 - Out-of-scope untouched
- **Given** `AsyncCombobox`/`AsyncMultiCombobox` (portal free-text type-ahead)
- **Then** they are unchanged, still used by the portal `SubmissionForm`, and NOT flagged by the ESLint ban.

## Definition of Done

- All AC pass (Phase-2 test report keyed to these ids).
- vitest covers: static filter, async fetch/debounce/stale-drop, selected-label survival, multi toggle/chips, clearable, grouping, disabled/empty/loading.
- playwright: at least one migrated form per domain cluster exercised FE→BE→DB; before/after screenshot for AC5.
- allowlist empty, `ui/select.tsx` deleted, grep-clean.
- doctrine docs updated; ESLint ban green in CI.
