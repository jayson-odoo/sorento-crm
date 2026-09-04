# PLAN - proforma invoice + packing list feedback batch (3 Sep 2026)

**Status:** APPROVED by the captain, 3 Sep 2026 ("okay good to go"), two lavish markup rounds. Rulings 1A, 2A, 3A, 4, 5 confirmed. UAC:
`scm-pi-packing-list-feedback-3sep-acceptance-criteria.md`. Feedback given on the
`loading-plan-feedback-2sep` lane (:3130) while testing PR #563; none of it is loading-plan work,
so it is its own lane and its own PR.

## Journey

See the UAC. Actor: purchasing, desktop. Fewest decisions: factory = line supplier, logo =
product brand, cartons / CBM per carton / totals derived, split follows the three typed costs.

## What was measured (3 Sep, lane code)

| Symptom | Cause (file:line) |
| --- | --- |
| Prev/next drops the tab | `ProformaInvoiceDetail.tsx:217` tab is `useState`; pager passes every non-reserved param through (`lib/listNavQuery.ts:67`), nothing reads it. Loading plan reads `?tab=` inline (`LoadingPlanView.tsx:59-169`). |
| Edit jumps to General | `beginEdit` calls `setTab('general')` (`ProformaInvoiceDetail.tsx:278`). |
| Product select empty in edit | Serializer emits `product_code` only, no `product_id` (`proforma_invoice_service.py:2884-2919`); `toDraft` hard-codes `productId: null` (`:148-166`). |
| **Save unbinds matched products** | `saveEdit` omits `product_id`; `_write_lines` writes `line.product_id = None` unconditionally (`:2484, :2528`). Silent data loss on every Save today. |
| UoM free text | `Input` at `:618`; master hook `useUOMSelectQuery` exists (`master-data-management/shared/hooks/use-uom-select-query.ts`), used by ProductForm + project-sales editors. |
| Match UX differs from loading plan | PI: dialog + deferred Forget, no Undo, no Remembered list (`:824-938`). Loading plan: `SupplierCodesTab.tsx` (535 lines) with in-place select, Undo, Dismiss, Remembered + Forget; queue endpoint is `plan_id`-scoped only (`fulfilment.py:283`). |
| Default filter `not_converted` | `ProformaInvoicesView.tsx:157` `useState('not_converted')` (AC-F6 of the Aug plan, now superseded). |
| Supplier dropdown dupes, no scroll | `/procurement/suppliers/select` = unordered, unpaginated `LIMIT 100`, labelled by name only (`procurement/suppliers.py:63-84`); lane DB holds real duplicate supplier rows (Hello x2, Testing Company x3). `CommandList` caps at 300px inside a Dialog-portaled popover (`command.tsx:52`, `SearchableSelect.tsx:362-385`). Same feed on `PlanContainerDialog.tsx:249` and the list filter. |
| Volume gauge on the PI | `ProformaVolumeFill.tsx` + `_fit()` (`proforma_invoice_service.py:2148-2182`); `container_size_id` lives on `scm.proforma_invoice`, nothing on `inbound_shipments`. A packing list is one container consolidating several PIs (FSCU8103365 = 7 factories), so the gauge sits one level too low. |
| Packing list `[object Object]` | `packingListService.ts:79-85` hand-rolls `new Error(error.detail)`; a 422 `detail` is an array. Most likely trigger: `shipment_date` sent raw (`''` 422s, `null` is accepted) at `packing-list-context.tsx:268`. Also `shipment_number` is silently dropped (`InboundShipmentUpdate` does not declare it, `schemas/procurement.py:308`), and a NaN carton count becomes `null` -> 422. |
| Download is the primary CTA | `packing-lists/[id]/layout.tsx:194-202`; Edit is in the gear (`:166-193`). |
| Shipment lines is a plain table | `PackingListLinesTab.tsx` uses `@/components/ui/table`, client sort, no `listingKey`. Columns: Product, Supplier, Qty, Material, Pcs/ctn, Cartons, L, W, H, NW, GW, CBM, From PI, SPO, Received, Status. |
| "Understand the formulas" | **Already built.** `consolidated_packing_list.py` (679 lines) is a cell-for-cell copy of the RMB sheet writing Excel formulas: `H = F/G`, `L = I*J*K/10^6`, `M = H*L`, `P = N*H`, `Q = O*H`, `U = T*F`; per-factory subtotals split by company (MOCHA separate); footer `Clearance = M_co/M_total * clearance_cost`, `China freight = M_co/M_total * china_freight_cost`, `Insurance = U_co/U_total * insurance_rate`. The three constants are `inbound_shipments.clearance_cost / china_freight_cost / insurance_rate` (Details tab, Costs card). |

## Rulings proposed (captain to confirm)

1. **Volume.** Push back on "not meaningful": the PI's total CBM is exactly the number she adds
   up to decide which invoices share a box, so the NUMBER stays. What goes is the capacity
   gauge and the Container size field on the PI: capacity is a property of the container, so
   the gauge and the size move to the packing list, and the convert dialog is where the size is
   chosen and the over-capacity check runs. One migration.
2. **Match stays in the row.** CAPTAIN RULED (3 Sep markup): the PI's own match (Match /
   Change / Forget in the Match column, plus the edit-mode Product select with Save) is the
   better experience, "edit, match, save; undo = edit, remove". No Supplier codes tab on the PI.
   What changes: the two paths become one memory - a product picked in edit mode is remembered
   as the supplier's code alias on Save (today it binds the line only, so the next invoice
   from the same factory does not auto-match), and clearing it forgets a manual alias.
   APPROVED A (3 Sep markup round 2). Loading plan keeps its tab: its rows are products ranked
   by demand, an unmatched code has no product row to sit under; the PI's rows are the supplier's
   own lines. Two shapes, one shared memory.
3. **Excel order is the screen order** for the packing list Details tab and the Shipment lines
   grid. The Split card is rendered from the same `build()` JSON the export uses, so screen and
   file cannot drift.
4. **Shipment lines: flat grid, one totals footer**, sorted Factory then No. Per-factory
   subtotal rows are an export concern; a grouped grid is a second mechanism for the same
   numbers. Revisit only if she asks for them on screen.
5. **DESCRIPTION** on screen and in the export stays the product master name (what the export
   does today). Carrying the supplier's own description from the PI onto the shipment line is a
   new column and a convert-time copy; parked in the backlog unless the captain wants it now.

## Slices (one lane, one PR; commits per slice)

| Slice | Scope | Phase 1 (FE mock) | Phase 2 (BE, test-first) |
| --- | --- | --- | --- |
| **S6** Packing list header + save | AC-F1..F6 | Edit primary, Download in gear (`layout.tsx`); `extractApiError` in the four service fns; `orNull` on dates, NaN guard; Details cards re-ordered per AC-F5 (`PackingListDetailsTab.tsx`, `packing-list-context.tsx` field lists). | `InboundShipmentUpdate.shipment_number`, `extra='forbid'` on the update schemas; pytest for both. |
| **S2** PI edit fidelity | AC-B1..B5 | `toDraft` carries `productId` / `productSetId`; select shows value; UoM `SearchableSelect` fed by `useUOMSelectQuery` (same cell shape as `SalesOrderDetail.tsx:808-846`). | Serializer emits `product_id` + `product_set_id`; `_write_lines`: absent key = keep, explicit null = unbind; pytest pins both (AC-B3). |
| **S1** Tab in URL | AC-A1..A5 | New `hooks/useUrlTab.ts` (tabs, default, basePath) extracted from `LoadingPlanView.tsx:59-169`; loading plan and PI both use it; `beginEdit` stops resetting the tab. | none (vitest only). |
| **S4** List default + supplier select | AC-D1..D5 | `placement` default `null`; empty-state copy; `getFulfilmentSuppliers` labels `code - name`, passes `page`, `SearchableSelect paginated pageSize 50`; reproduce the no-scroll in a Dialog with agent-browser and fix at `SearchableSelect` if real. | `/procurement/suppliers/select` ordered + paged + `has_more`; pytest. |
| **S3** PI match memory parity | AC-C1..C4 | Edit-mode Product select `clearable`; Match column unchanged. | `_write_lines`: a changed product upserts a `manual` alias via `supplier_code_alias_service` and re-binds sibling lines; an explicit null deletes a manual alias; pytest AC-C1/C2. |
| **S5** Volume to the container | AC-E1..E6 | PI General: `ProformaVolumeFill` becomes a number + unmeasured count; Container size field removed; convert dialog gains the size select; packing list Container card gets the gauge (reuse `ProformaVolumeFill` renamed `ContainerVolumeFill` under `components/common`). | Migration: add `inbound_shipments.container_size_id`, copy from single-PI drafts, drop `proforma_invoice.container_size_id`; `_fit` moves to the shipment payload; convert takes `container_size_id`; `_over_capacity` uses it; pytest AC-E6. Both manual dict builders checked (new column reaches the FE). |
| **S7** Shipment lines DataGrid | AC-G1..G7 | `PackingListLinesTab.tsx` rebuilt on `DataGrid` with the workbook columns, derived cells, footer, Split card fed by `usePackingListBuild` (`GET .../packing-list`). | none new; the JSON endpoint exists. |

Order: S6, S2 (both stop data loss / a hard error), S1, S4, S3, S5, S7. S7 is largest and last
because S5 changes the header it sits beside. Ruling 1 confirmed by the captain (3 Sep markup):
convert checks the COMBINED cbm of the selected invoices against the chosen container size.

## Lane

Branch off `origin/main` AFTER #563 merges (the lane's `proforma_invoice_service.py` changes land
first; stacking on the lane branch would make a dead-base PR). Stack slot :3130/:8130 reclaimed
from the loading-plan lane once merged. Coder on Sonnet per slice, worktree isolation; reviewer
on Opus at the end.

## Backlog (deferred)

- Supplier description carried PI -> shipment line (ruling 5).
- Per-factory subtotal rows on screen (ruling 4).
- Dedupe the real duplicate supplier rows in the lane DB (test data, not code).
- `ClearanceDeliveryCard.tsx` looks unmounted; delete in S6 if confirmed dead.

## DoD gate

Mock swapped to real; existing shipments carry `container_size_id` NULL = tenant default;
new column in both manual dict builders; real sidebar clicks at 375 and 1280; agent-browser
evidence run per slice; pytest + vitest green; `alembic heads` single before PR.

## Round 2 (captain, 3 Sep, after printing from production)

Measured against the fixture `documentation/plans/scm/fixtures/FSCU8103365.xlsx` (sheet RMB):

| Symptom | Cause |
| --- | --- |
| Export header block centred, values wrap (`FSCU8103365` on two lines, dates print `######`) | `to_xlsx` applies `Alignment(center, center, wrap_text=True)` to the header rows (`consolidated_packing_list.py:445`); the fixture's header labels are default (left) and values are `horizontal=left`, no wrap, so a long value overflows into C. Column B is 7.3 wide in both files; the wrap is the difference. |
| "Freezing at the bottom" on first open | `ws.freeze_panes = A17` (`:668`); the fixture has NO freeze pane. |
| DESCRIPTION prints the product name (= the code on prod) | shipment line has no description column; the PI line's supplier wording is dropped at convert (was BL-045, captain now wants it). |
| Qty input loses focus after two digits; picked product does not show on a new line | S7 grid: inputs remount on every keystroke (draft state change rebuilds column defs / cell components), same class as the S3 columns-memo fix. |
| Ctn qty reads `-` on a line with no pcs/ctn; cannot change an existing line's product | Ctn qty is derived only; existing line's product is fixed by design of the old table. |
| Is the SORENTO + MOCHA split right? | Export fidelity test pins the fixture (which carries MOCHA blocks); Split card is unit-tested on the same numbers; not yet checked live on a mixed container. |

Slices, same PR (#594), after S5:

| Slice | Scope |
| --- | --- |
| **S8** export fidelity | Header rows: label cells default alignment, value cells left, no wrap, dates as real dates with the fixture's number format; no freeze pane; fidelity test extended to assert alignment, wrap and freeze against the fixture cell by cell. |
| **S9** description carried | Migration 466: `inbound_shipment_lines.description` Text NULL; convert copies `proforma_invoice_line.description`; backfill existing lines from `scm.proforma_invoice_shipment_link`; editable in the lines grid; export column D = description, else product name; screen Description column reads the same. |
| **S10** lines grid editing | Inputs keep focus across keystrokes (test types three digits); product select on a new line shows the pick; product editable on an existing line (unique index shipment+product+supplier still enforced, duplicate refused with a readable message); Ctn qty editable (`cartons_count`) when pcs/ctn is blank, derived and read-only when pcs/ctn is given; every measurement cell fillable on every row. |
| **S11** mixed-company check | Tester: on :3140 build a packing list with a MOCHA-brand line beside SORENTO lines, compare Split card, Download XLSX footer and a hand calculation (clearance/freight by cbm share, insurance by amount share); report numbers side by side. |

### S12 (from the S11 check, 3 Sep)

Measured: `consolidated_packing_list.build()` resolves a line's CBM as stored `cbm`, else the product
master's dimensions, never the line's own carton dimensions (`:141-143`), while `to_xlsx` writes
`=H*L` live from those dimensions. A line typed with L/W/H and no stored cbm is 0 cbm on screen and
gets no clearance / freight share; the workbook is right. `_attach_capacity` (S5) sums the same
stored `cbm`, so the gauge has the same hole. The Costs card sends an emptied field as "not
stated" (`orUndefined`) so a cost cannot be cleared from the UI.

Slice: ONE server-side rule `line_cbm(line, product)` = stored `cbm`, else `ctn * L*W*H/1e6` with
`ctn = qty / pcs_per_carton` when pcs is stated else `cartons_count`, else catalogue; used by
`build()`, `_attach_capacity` and anywhere else that sums shipment-line volume. `build()` gets its
own tests (JSON payload, mixed company, dims-only line). Costs card: empty sends `null`.
