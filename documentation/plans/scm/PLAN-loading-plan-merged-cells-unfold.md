# PLAN: Loading plan - stock list merged cells read through, no-demand rows back in the one table

Status: BUILDING (owner go 15 Sep 2026)
Domain: scm
Branch: fix/loading-plan-merged-cells-unfold
UAC: loading-plan-merged-cells-unfold-acceptance-criteria.md
Owner feedback: 15 Sep 2026, CHAOZHOU JINBAICHUAN plan, stock list of 14/09/2026 (121 model rows)

## What the owner saw

1. Supplier codes tab, "Supplier says" column: MWB247 reads only `M`. On the supplier's sheet
   the 品名 cell `盆小孔` is merged over three rows (SRTWB247, MWB247, CGB247). openpyxl hands the
   anchor row the value and every covered row `None`, and `supplier_inventory_reader.read_workbook`
   reads cells raw, so the two covered rows lose 品名 - and also 体积 (H86:H88 merged, 0.03).
2. Lines tab: "18 products held with no open demand" sits under a collapsed line below the
   ranked grid (S5, 2 Sep). Owner: one table, otherwise those rows get overlooked.

Measured on the real file (`/Users/tehjayson/Desktop/Stock list (1).xlsx`, not committed):
122 merged ranges; text merges in 品名 (E86:E88, E89:E90), quantity merges in 空瓷 (G86:G88 = 2,
G89:G90 = 3549), cbm merges in 体积 (H86:H88, H89:H90, H97:H102) and total cbm (I86:I88 = 8.16).

## Decisions

- **Fix the reader, do not add an edit box.** Each stock list upload deletes and reinserts every
  `supplier_inventory` row for the plan (`supplier_inventory_service.apply`), so a hand edit dies
  on the next upload. The merge is the only cause seen; trigger for an editable "Supplier says"
  is a case that survives this fix.
- **Which merged columns fill through:** text fields (`product_name`, `brand`, `spec`, `remark`)
  and `cbm_per_unit` - a body property, the same for every model in the family. **Quantities do
  not fill:** `qty_packed`, `qty_unfinished`, `cbm_total` stay on the anchor row only. A merged
  `空瓷 2` over three rows is one figure for the family; copying it triples the count.
- **Where:** a `sheet_merges(file_data)` helper beside `sheet_rows` in
  `app/services/scm/outstanding_reader.py`, returning `{(row, col): (anchor_row, anchor_col)}`
  for xlsx (opens the workbook NOT read-only - `ReadOnlyWorksheet` has no `merged_cells`, verified
  on openpyxl 3.1.5) and `{}` for OLE2 `.xls`. `read_workbook` in `supplier_inventory_reader.py`
  applies it after header detection, per mapped field, only for the fill-through fields above.
  No other reader changes behaviour.
- **Fold removal:** `ContainerRequestSection.tsx` renders ONE grid over `displayRows`. The
  `has_demand: false` rows keep their muted styling and blank rank and sort after every ranked
  row (AC-N5 comparator already does this). The `Collapsible`, `foldOpen`, `foldPagination`,
  `foldSorting`, `rankedRows`, `foldedRows` and the second grid go. Search (AC-N3) and the typed
  qty on a no-demand row (AC-E3) keep working because the rows are the same objects in the same
  grid.

## S3 (owner, 15 Sep, second message): split Suggested qty from Requested qty

Owner: "every time we change the suggested quantity manually, we forgot what's the original
suggested quantity". Today ONE column, "Suggested qty", holds the input, and the input shows the
override, so the formula's answer is only in the cell's hover title.

Measured: `build_for_plan` already emits `engine_qty` (the untouched formula answer) beside the
overridden `suggested_qty`, it is typed on `ContainerRequestRow` (`fulfilmentService.ts:682`)
and `LoadingPlanView` already uses it for Save (N). No backend change.

- "Suggested qty": read-only text, `engine_qty`, sortable, keeps the `FormulaTip` and the
  hover formula. Muted when a no-demand row.
- "Requested qty": the existing input (`renderQtyCell`, `qtyFor` / `onQtyChange`), column id
  `requested_qty`, sortable on `qtyFor(row)` is NOT needed - sort on `row.suggested_qty` (the
  saved override, what the record holds) as the old column did. Sits right after Suggested qty,
  before Remarks. Read-only plan (cancelled) renders it as plain text (it used to be a disabled input; AC-Q4 governs). The per-cell formula hover sits on the Suggested qty cell, the one showing the engine figure.
- Same row object, same `row_key`, so search, Save (N), the stat cards and the row dialog are
  unchanged. Column-preference store: a saved visibility set must not hide the new column
  (check how unknown ids default in `useListingColumnConfig` / the DataGrid personalisation).

## Out of scope

Editable "Supplier says"; `.xls` merged cells; any change to `sheet_rows` callers
(`po_listing_reader`, `packing_list_reader`, `purchase_history_reader`).

## Slices (one PR)

- S1 backend: `sheet_merges` + fill-through in `read_workbook` (pytest, file-only via injected
  `AliasResolver`, synthetic workbook with the exact merge shape above).
- S2 frontend: un-fold (vitest on `ContainerRequestSection`).
- S3 frontend: Suggested qty (read-only, engine_qty) + Requested qty (input) columns (vitest).
