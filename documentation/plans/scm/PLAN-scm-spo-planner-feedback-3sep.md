# PLAN - SPO planner feedback, 3 Sep 2026

**Status:** DRAFT, captain's screenshot round 3 Sep 2026 (evening). UAC:
`scm-spo-planner-feedback-3sep-acceptance-criteria.md`.
Lane: `feat/scm-spo-planner-feedback-3sep`, worktree `.claude/worktrees/spo-planner-3sep`,
stack FE :3160 / BE :8160, Redis db 14. **Stacked on `feat/scm-loading-plan-lightbox-3sep`**
(a4256ce9e): six of the asks in this round already ship there (S3 header context removed, S4
SPO status pill + Container column, S6 Outstanding / Delivery date words) and every remaining
slice edits the same two files. PR opens against main only after the lightbox PR merges
(retarget + CI first, never a stacked PR into a dead base).

**Amends:** `PLAN-scm-fulfilment-doctrine-correction` (the SPO planner, `SpoPlannerTable.tsx`,
`spoScheduleMatrix.ts`, `SpoScheduleMatrixTable.tsx`) and the shared
`scm/components/PlanRowDialog.tsx` pickers.

## 1. What the captain saw (prod, draft shipment, JINBAICHUAN)

| Screenshot | Symptom | Cause (source on the lightbox lane tip) |
| --- | --- | --- |
| Planner header | "Draft shipment - based on this draft's own packed quantities, not a real packing list yet." | `SpoPlannerTable.tsx` CardHeader `<p>` under the title, both wordings. |
| Toolbar | Grey sentence "248 ticked, 19 on this container - SO336600 partly covered; ..." wraps two lines | `partlyCovered` banner, `SpoPlannerTable.tsx:1043-1053`. |
| Toolbar | Expand all / Collapse all jump between the middle and the right edge | The toolbar is one `justify-between` flex row with 2 or 3 children; the banner's presence decides where the middle child lands. |
| Product cell | Second line "CGB247 · CHAOZHOU JINBAICHUAN SANI..." | `product_name` (= item code for this master) + supplier, `:620-623`. |
| PO covers cell | "1 of 1 POs" under the number | `:648-650`. |
| Schedule toolbar | "Bucketed by" + "PO coverage (PO's expected date)" wraps two lines, sits mid-row | `Label` + `SearchableSelect` in `w-52`, `:1025-1040`. |
| Schedule row | Product code repeated under itself | `row_description: ln.product_name`, `:815`/`:851`. |
| Schedule cell | Hover popover; no colour; no lightbox | `SpoScheduleMatrixTable.tsx` `Popover` per cell, `:140-160`. |
| SO covered dialog | "408 of packed 408" beside the title; product code repeated as description | Context = lightbox S3 (already gone). Description = `PlanRowDialog` `DialogDescription` prints `productName ?? productCode`, `:950`. |
| SO covered dialog | No search / filter; headers Required, Open | `SoCoveragePicker` is a plain `DocTable`, `:841-920`. |
| PO covers dialog | Headers Due, Open | `PoTakesPicker` `DocTable`, `:784-787`. Lightbox S6 renamed `PoTabs` only. |
| SPO history dialog | Packing list column reads Draft; status raw | **Done on the lightbox lane (S4).** Verified in the evidence run only. |

### Answered: the closed loop

"After I create an SPO, is the PO or SO it covered considered consumed, and will the next
planner for the same product show it?" Today the loop is closed by **netting, not by
showing**:

| Side | How `create` records the take | How the next `suggest` reads it | Test |
| --- | --- | --- | --- |
| PO line | Advances the source line's `qty_received` by the pull and writes the SPO line's `source_ref.pulls` | `_open_line_rows` offers `qty_ordered - qty_received`; a fully pulled line is not offered | `test_an_spo_take_does_not_come_off_the_line_twice`, `test_the_purchase_order_says_which_spo_took_its_quantity` |
| Retail SO line | `source_ref.so_coverage` on the SPO line | `_retail_covered_qty` nets each line; a fully covered line is dropped from the list | `test_a_retail_line_already_covered_by_one_container_is_offered_net_on_the_next`, `test_a_partly_covered_retail_line_is_offered_for_the_rest` |
| Project OI row | `OrderInquiryLink` rows via `place_on_po_allocations` | `_project_coverage` nets each row against its links | `test_a_project_row_already_linked_elsewhere_is_offered_only_for_what_is_left` |
| Unwind | Delete SPO removes lines, links, allocations | Rows return to the next planner in full | `test_unwind_deletes_po_lines_headers_links_and_allocations_then_suggest_recovers` |

So the operator cannot plan against an occupied PO or SO, but they also cannot SEE that it is
occupied: the row simply vanishes (or shrinks) with no word about where it went. S5 makes the
occupied portion visible and grey, exactly as the captain proposed, without changing the
netting or the cascade.

## 2. Slices

### S1. Planner chrome: fewer words, controls that stay put (FE)

`SpoPlannerTable.tsx` only.

- Drop the sentence under "SPO planner" (both wordings). The title stays.
- Drop the grey `partlyCovered` sentence. The two red conditions stay (`splitMismatch`,
  `overTicked`): they gate Create SPO, so they are a state the operator must act on.
- Product cell = code + info icon only. No second line.
- PO covers cell = the number only. No "N of M POs".
- Toolbar is two fixed groups. **Left:** the Table / Schedule toggle, then Expand all /
  Collapse all (table view only) in the same group so they never move. **Right:** in schedule
  view the View select; in table view the red condition text, if any. Nothing is centred.
- Schedule control: label **View**, options **Purchase order** / **Sales order**, one line
  (the select is wide enough for the longer option; no wrap at 1280 or 375).
- Schedule row header: code only (`row_description: null` from the planner). The matrix
  table already renders no second line when `description` is null.

### S2. Lightbox description only when it says something new (FE, foundation)

`PlanRowDialog.tsx` shell.

- `DialogDescription` renders visibly only when `productName` is non-empty AND differs
  from `productCode` (case-insensitive, trimmed). Otherwise it renders `sr-only` with the
  code, so Radix still has its description and nothing repeats on screen.
- Every dialog in the family inherits this (loading plan, planner, reorder), which is the
  point: the repeat is a data fact (`product_name == item_code` on this master), not a
  planner bug.

### S3. Pickers: the family's words, and a search + filter toolbar (FE)

`PlanRowDialog.tsx` `PoTakesPicker` and `SoCoveragePicker`.

- Headers: SO picker **Required → Delivery date**, **Open → Outstanding**. PO picker **Due →
  Delivery date**, **Open → Outstanding**. Same words `PoTabs` took in lightbox S6 and the
  purchase-order list heads its columns with.
- Both pickers become a `DataGrid` (`tableLayout: { width: 'fixed', columnsResizable: true }`,
  `columnResizeMode: 'onChange'`, sticky header, explicit `size` per column, `truncate` +
  `title` on Customer / Supplier), the same shape `spoColumns` / `poColumns` already use
  inside the SPO and PO dialogs on this lane. The tick column stays a `Checkbox` bound to
  `tickedIds` / `tickedKeys`; the footer line stays.
- `DataGridListToolbar` above each grid: `searchSlot` = the same search input the users list
  renders (icon, Enter to apply, clear X); `filters={{ kind: 'custom', ... }}` = the users
  list's "Advanced filters" popover with condition rows (field select, value select, remove),
  Apply / Clear filters. Filtering is client-side over the rows the picker already holds.
  - SO picker fields: Sales order, Customer, Class (Project / Retail), Location. Search
    matches Sales order and Customer.
  - PO picker fields: PO, Supplier. Search matches PO and Supplier.
  - A filtered-out row keeps its tick; the footer states ticked / covered over ALL rows, and
    adds "· N of M shown" only while a filter or search is active.
- `exportConfig={false}`, no column personalization (no `listing_key`): these are a
  container's own rows, not a listing.

### S4. Schedule cells: colour, and click opens the standard lightbox (FE)

`SpoScheduleMatrixTable.tsx`, `spoScheduleMatrix.ts`, `SpoPlannerTable.tsx`.

- A cell this SPO takes from is tinted `bg-primary/10` with `font-semibold` on the figure,
  the peak-cell tint lightbox S1 introduced; the row Total keeps its plain style. A cell that
  is only occupied by another SPO (S5) is `bg-muted text-muted-foreground`. A cell with both
  shows our figure tinted, and a muted second line `+N on SPO-…` (number of the other SPO,
  first if several).
- Clicking a cell opens `PlanRowDialog` for that shipment line, `kind='po_takes'` in the
  Purchase order view and `kind='so_coverage'` in the Sales order view: the SAME dialog the
  table's PO covers / SO covered cells open, on the same `dialog` state. The hover `Popover`
  is removed. The matrix entry carries `shipment_line_id` so the click can find its line.
- Inside the opened picker, rows whose date falls in the clicked week bucket carry
  `data-bucket-hit` and the `bg-primary/10` row tint, so the click reads as "these rows";
  the picker's search / filter is untouched by it.
- Keyboard: the cell is still a `button`; Enter / Space open the dialog.

### S5. Occupied by another SPO: shown grey, never tickable (BE + FE)

Backend `spo_conversion_service.suggest` payload, additive only. The cascade, the default
ticks, `qty` semantics and `create` are untouched.

- `so_coverage[]` entries gain `taken_qty: float` and `taken_by: string[]` (SPO numbers,
  oldest first). Source: retail = `_retail_covered_qty` widened to also return the SPO
  numbers (`PurchaseOrder.po_number` of the `crm_spo` line whose `source_ref` names the SO
  line); project = `OrderInquiryLink` rows joined to their `spo_allocations` → SPO line → PO
  number. A row FULLY taken is now **returned** with `qty: 0`, `default_ticked: false`, its
  `taken_qty` / `taken_by` filled, in its normal date position. Today it is dropped.
- `po_takes[]` entries gain `taken_qty` and `taken_by` the same way, read from the SPO
  lines whose `source_ref.pulls` name the PO line (the same read
  `PurchaseOrderService._allocations_for` does for the PO panel, reused not copied: extract
  the "pulls by source PO line" query into one helper both call). A PO line to this supplier
  and product with `open == 0` whose only reason is prior pulls is **returned** with
  `qty: 0`, `open_qty: 0`, `taken_qty > 0`. A line with nothing open and nothing pulled
  (genuinely received) is still not offered.
- Frontend: a row with `qty === 0 && taken_qty > 0` renders grey (`text-muted-foreground`),
  its checkbox disabled and unticked, and a **Taken** column (`taken_qty`) with the SPO
  number(s) as `title` and under the figure in `text-2xs`. Partly taken rows show both
  figures (Outstanding = what is left, Taken = what is gone). `poCoveredFor`, `coverageTakes`,
  `defaultSoKeys`, `cascadeTake` skip `qty <= 0` rows (they already do: `min(0, left)` is 0).
- Schedule: the occupied quantity buckets by the same date into the grey cells of S4.
- Pytest (test-first, `tests/scm/test_spo_planner_selection.py`): fully covered retail line
  returns on the next container as taken with the first SPO's number; partly covered line
  carries both figures; project row linked elsewhere carries `taken_by`; PO line fully pulled
  by SPO-1 is returned as taken on a second shipment's planner and the cascade takes nothing
  from it; after `unwind` of SPO-1 the same rows come back with `taken_qty: 0`.
  `test_route_spo_suggestion_happy_path` asserts the two fields on the response model
  (`response_model` drops undeclared fields).
- Vitest: grey row untickable; ticked figures ignore taken rows; a cell with only taken
  quantity renders grey and opens the dialog.

### S6. Tests, browser evidence, review

- Vitest: `SpoPlannerTable.test.tsx` (no subtitle, no partly-covered sentence, toolbar
  groups, View labels, no row description), `PlanRowDialog.test.tsx` (description rule,
  picker headers, filter narrows rows and keeps ticks, taken rows), matrix table test (tint
  classes, click opens dialog).
- agent-browser evidence run on :3160 via the sidebar: Procurement → Packing lists → a draft
  shipment → SPO planner; both views; open a cell; filter in the SO picker; screenshot each.
- Full `npm run test`, whole-frontend `npx tsc --noEmit`, `pytest tests/scm/test_spo_planner_selection.py tests/scm/test_spo_conversion.py`, `alembic heads` (no migration in this batch).
- Opus review, then ONE PR after the lightbox PR merges.

## 3. Not in scope

- Week granularity toggle on the schedule (still the follow-up the doctrine plan named).
- Filtering the SO picker by date range (the schedule click answers that).
- Any change to the cascade, default ticks, or what `create` writes. Netting stays the rule;
  S5 only makes it visible.
- The SPO history dialog (lightbox S4 covers it).

## 4. Order

S1 → S2 → S3 → S4 → S5 (BE test-first, then FE) → S6. One coder at a time in this worktree.
