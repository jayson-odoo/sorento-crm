# PLAN: AutoCount pull - Compare tab shows every difference it counts

Status: built, review READY, browser pass pending. Track: **small fix track** (one seam, FE
only, no migration, no auth change; one coder writes tests + fix, one reviewer, browser pass on
the changed screen).
UAC: `autocount-compare-tab-detail-acceptance-criteria.md`.
Follows: `PLAN-autocount-pull-review.md` P11 (Compare with my Excel).

## Defects (prod compare, 22 Sep, SRT products)

Seam: `sorento_crm_frontend/app/(protected)/system-management/import-jobs/autocount-pull/components/PullCompareTab.tsx`.
Backend `autocount_pull_compare.py` is correct and unchanged.

1. **Booleans render blank.** `is_active` differences carry JSON `true` / `false`; the cell
   renders `{row.original.excel}` (`:117-119`, `:127-129`) and React prints nothing for a
   boolean. The download writes TRUE / FALSE. ~700 rows on prod looked empty on both sides.
2. **"709 differ" vs 710 downloaded rows.** `summary.different` counts ITEMS with at least one
   differing field (`compare.py:137`); the grid and download hold one row PER FIELD
   (`:128-131`). One item differed on two fields. The headline never says which count it is.
3. **"100 only in your Excel, 175 only in AutoCount" has no detail.** The response carries the
   two item-code lists (`only_in_excel`, `only_in_pull`, `compare.py:139-140`,
   `AutocountComparePullResult` in `types/autocountPull.types.ts:123`); the tab shows the counts
   only, and the download omits them.

## Design

All in `PullCompareTab.tsx` (+ a tiny pure helper module beside it so it is unit-testable):

- `formatCompareValue(field, value)`: boolean -> `Active` / `Inactive` (the only boolean field
  is `is_active`); `null` / `undefined` -> `-`; number/string -> `String(value)`. Used by the
  two value cells, their `title`, and the download rows.
- `fieldLabel(field)`: `description` -> Description, `item_group` -> Item Group, `item_brand`
  -> Item Brand, `price` -> Price, `is_active` -> Active, `on_hand_qty` -> On Hand Qty,
  unknown -> the raw key. Cursor rule: no snake_case in the UI.
- Grid rows = `differences` + one row per `only_in_excel` code (`field` = "Only in your
  Excel", excel `Present`, pull `Missing`) + one row per `only_in_pull` code (`field` = "Only
  in AutoCount", excel `Missing`, pull `Present`). Stock labels are `code|location`: split on the
  first `|` into `item_code` / `location`. `recordCount` and the download use the SAME combined
  array, so what is counted is what is downloaded.
- Headline body: `"709 items differ (710 differences), 100 only in your Excel, 175 only in
  AutoCount."`; when the two numbers are equal just `"N items differ"`. `total` / `matched`
  wording unchanged.
- Download file: same columns, values formatted by `formatCompareValue`; only-in rows included.

No backend change: the response already carries everything.

## Tests (vitest, `PullCompareTab.test.tsx` + `compareRows.test.ts`)

- boolean difference renders `Active` / `Inactive` in both cells and `title`.
- headline reads `2 items differ (3 differences)` for a fixture with one two-field item.
- only-in codes appear as grid rows with the labels above; stock `code|location` splits.
- `generateExcelFile` (mocked) receives differences + only-in rows, booleans formatted.
- field labels are human (`Active`, not `is_active`).
- existing PullCompareTab tests stay green.

## Browser pass

agent-browser on the lane stack (BE :8080, FE :3080 `next dev`, fake gateway :8099 fixtures,
clone `sorento_acpull_e2e`): products compare with a file holding one is_active flip, one
two-field item, one code missing each side; 1280 + 375. Evidence under
`documentation/plans/autocount/evidence/autocount-compare-tab-detail/`.
