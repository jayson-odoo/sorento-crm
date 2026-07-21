# PLAN — Searchable Dropdown Standard

> UAC: [`searchable-dropdown-standard-acceptance-criteria.md`](./searchable-dropdown-standard-acceptance-criteria.md) (contract; grill-locked).
> Governs: `PRINCIPLES.md` > `ADR-PRODUCT-STANDARDS.md`. FE-only.

**Status:** PHASE 1 DONE, PR open on `feat/searchable-dropdown-standard` (branched off `main`).
Component upgraded + ESLint ban + allowlist (133→131) + reference migrations
(`LookupSetFormDialog`, `BindingAddDialog` — 4 dropdowns). Browser-verified on a prod build via
the sidebar: search filters, selection commits, dependent dropdown unlocks, 0 console errors.
Against main baseline: lint errors 318→318 (this rule contributes 0; +7 intentional `warn`-level
native-`<select>` advisories), `tsc` clean in all touched files, no new vitest failures.

Phase 2 (staged domain migrations + tests) starts with **master-data-management (8 files)**.

Carve-out note: this work originally sat uncommitted on the stale `fix/pr-rejected-by-uuid`
branch (92 commits behind). Re-applied cleanly onto `main`; `useLookupSets.ts` was deliberately
NOT carried over — the stale copy would have reverted `useSetBindingDefaultValue`, added to main
in the interim.

### Corrections to this plan, learned in Phase 1

- **Baseline was wrong.** Plan said "start 118 (110 + 8)". The real auto-seeded allowlist was
  **133**. The 8 bespoke `*Combobox.tsx` slated for folding-in **no longer exist** on `main` —
  that planned work has already evaporated. Burn-down metric is 131 → 0.
- **Select all is doctrine for multi-select** (added Phase 1, not in the original plan). Acts on
  the *visible* (filtered) rows, skips `disabled`, and in async mode labels itself
  "Select all N loaded" because it can only see the fetched page. To know the visible set the
  component had to own filtering, which moved static matching from cmdk fuzzy scoring to
  all-tokens substring.
- **The in-dialog risk was clipping, not the focus trap.** `PopoverContent` does not portal, and
  `dialog-content` is `overflow-y-auto`, so a popover that flips to `side="top"` is laid out at
  correct coordinates but never painted — the search box silently disappears.
  `getBoundingClientRect` reports it as on-screen, so only a screenshot catches it. Fixed via a
  new `PopoverPortal` used by the two standard components only. **Phase 2 migrates ~25 more
  in-dialog dropdowns — screenshot each, don't trust DOM assertions.**
- **A green lint proves nothing about coverage.** `BindingAddDialog` sat unmigrated on an
  already-"done" page because it was grandfathered in the allowlist. Per-PR completion check must
  be `grep` over the whole domain folder, not the lint result.

## Goal

One searchable dropdown standard, everywhere. Kill the 3-way fragmentation (110 non-searchable
Radix Selects + 8 bespoke comboboxes + underused shared component). Make "all dropdowns searchable
via the standard component" enforced doctrine.

## Current state (measured)

- `@/components/ui/select` (Radix, **not searchable**): **110 files**, 0 use react-hook-form, 3 use `SelectGroup`.
- `components/common/SearchableSelect.tsx` (static, Command+Popover): 2 usages. **Gold-standard seed.**
- `components/common/SearchableMultiSelect.tsx`: 0 usages.
- 8 bespoke popover-pick `*Combobox.tsx`: Warehouse, Product×2, PackingList, Supplier, ProductComboboxSearchable, Brand, Category → **fold in + delete**.
- `AsyncCombobox`/`AsyncMultiCombobox` (portal free-text type-ahead, portal `SubmissionForm`): **out of scope, untouched, not banned**.
- Raw `<select>`: 1 file.

## Target component API

`components/common/SearchableSelect.tsx` (single) + `SearchableMultiSelect.tsx` (multi), shared
internal trigger/popover/list skin.

```ts
type Option = {
  value: string; label: string;
  searchText?: string; description?: string; group?: string;
  disabled?: boolean;                              // per-option disabled (Radix SelectItem disabled parity)
};

// single
type SearchableSelectProps = {
  value: string;
  onChange: (value: string) => void;
  options?: Option[];                              // static mode
  fetchOptions?: (q: string) => Promise<Option[]>; // async mode (mutually exclusive with options)
  selectedOption?: Option;                          // async: label survival when value not in fetched page
  clearable?: boolean;                             // default false; explicit × when true
  size?: 'sm' | 'md' | 'lg';                        // shared selectTriggerVariants (default md)
  placeholder?: string; emptyMessage?: string; disabled?: boolean;
  className?: string; triggerClassName?: string;
  renderTriggerLabel?: (opt: Option) => React.ReactNode;
  renderOption?: (opt: Option) => React.ReactNode;  // custom option body (status dots, icons)
};
// multi: value: string[]; onChange: (v: string[]) => void; same modes; chips in trigger; toggle-select;
//        selectedOptions?: Option[]  (async label survival, plural)
```

Mode branch: `fetchOptions` present → async; else static client-filter over `options`.
**Guard:** neither `options` nor `fetchOptions` → render disabled trigger + `emptyMessage` (never crash).

### Trigger parity mechanism (concrete)
`selectTriggerVariants` (cva) already lives in `ui/select.tsx` but isn't exported. **Extract it to
`components/common/select-trigger-variants.ts`**; import it from BOTH `ui/select.tsx` (until deleted)
and the standard. Parity is then structural (one source), not a copy that can drift.

## Trigger parity (D4 / AC5)

Adopt Radix `SelectTrigger`'s exact classes so migration = zero visual diff. From `ui/select.tsx`:
- base: `flex bg-background w-full items-center justify-between border border-input shadow-xs shadow-black/5 text-foreground data-placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 [&>span]:line-clamp-1` + aria-invalid/data-invalid variants.
- size: `sm h-7 px-2.5 text-xs`, `md h-8.5 px-3 text-[0.8125rem]`, `lg h-10 px-4 text-sm`.
- Current `SearchableSelect` uses hand-styled `h-10` → **replace** with these variants + `size` prop. Extract to a shared `selectTriggerVariants` so both `ui/select` (until deleted) and the standard share one source; verify with before/after Playwright screenshot.

## Enforcement (D5 / AC12–13)

1. ESLint `no-restricted-imports`: ban `@/components/ui/select`; ban raw `<select>` (`no-restricted-syntax` on `JSXOpeningElement[name.name='select']`); ban `CommandInput` import outside `components/common/*` + `components/ui/*`. Message → "Use SearchableSelect/SearchableMultiSelect — see ADR-PRODUCT-STANDARDS.md".
2. **Shrinking allowlist** (`overrides` block or a tracked ignore list) grandfathering all 110 + 8 bespoke on day 1; each migration PR deletes its entries.
3. `PRINCIPLES.md` hard-fail rule + `ADR-PRODUCT-STANDARDS.md` doctrine + `CLAUDE.md` FE-layering note.
4. Allowlist → 0 → **delete `components/ui/select.tsx`** + 8 bespoke files.

## Phases

### Phase 1 — Component + reference migration (one PR)
- Upgrade `SearchableSelect` + `SearchableMultiSelect`: async mode, `selectedOption`, `clearable`, `group`, `size`, pixel-match trigger, remove re-click-deselect.
- Land ESLint ban + full allowlist (all 110 + 8 grandfathered) + doctrine docs.
- Migrate **one reference form** (e.g. a master-data create modal) off Radix Select → screenshot before/after (AC5).
- No test yet beyond smoke (contract may shift on review). Browser-verify via sidebar.

### Phase 2 — Staged domain migrations + tests
One PR per domain cluster (procurement, master-data, user-management, sla, complaints, forms, marketing, inventory, system…). Each:
- Transform Radix Select JSX-children → `options[]` (static default per D7). Switch to async only where list large + endpoint exists.
- Migrate that domain's bespoke comboboxes; delete them.
- Delete the domain's files from the allowlist.
- **Tests land here:** vitest (static filter, async fetch/debounce/stale-drop, selected-label survival, multi chips/toggle, clearable, grouping, disabled/empty/loading) + playwright (one migrated form per cluster, FE→BE→DB).
- Browser-verify each migrated form via sidebar.
- Final PR: allowlist empty → delete `ui/select.tsx` → grep-clean assert (AC13).

### Phase 3 — Code review
`/code-review` on the accumulated diff. Confirm: zero visual diff sampled, tests present, allowlist empty, doctrine docs in, out-of-scope `AsyncCombobox` untouched (AC15).

## Risks / notes

- **JSX→props transform is not pure syntactic** (grouped items, icon items, custom-rendered `SelectItem`). Hand-review each; staged PRs keep this reviewable.
- **Async label survival** is the subtle correctness trap — every async caller must pass `selectedOption` or the trigger goes blank on load (AC4). Enforce in review.
- **Popover-in-dialog focus trap** — verify Command-in-Popover-in-Dialog keyboard works (AC10/11); shadcn pattern supports it.
- Don't balloon into backend search-endpoint work (D7) — static client-filter is the default; async is opt-in.

## Migration tracking

Allowlist length = burn-down metric. Start 118 (110 + 8). Each PR logs count removed. Done at 0.
