# PLAN - SPO planner feedback, 3 Sep 2026

**Status:** IMPLEMENTED (rounds 1 + 2, review round 2 folded) - PR #623. UAC:
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

**Review round (Opus review of S5 BE / S7, 3 Sep 2026, fix round):** F1 (blocker) - a pin to
an exhausted PO line no longer fell back to the product match. F2 - a taken-only `po_takes`
row was appended for any candidate with `taken_qty > 0` regardless of its own open balance,
greying out lines with real balance left. F3 - `_project_coverage`'s `taken_by` only ever
named an SPO, though `taken_qty` already summed every link including a plain PO placement.
F4 - dead `_retail_covered_qty` deleted. F6 - `coverage_for_so_lines`'s `qty` used `_g`
(drifts to scientific notation, disagrees with the order-inquiry link's own formatter) rather
than a fixed-point read. F7 - `_spo_pulls_by_po_line` re-scanned the whole `crm_spo` book once
per shipment line rather than once per `suggest` call. F9 (pre-existing) - `unwind` bulk-deleted
`spo_allocations` an `OrderInquiryLink` pointed at, violating `ck_order_inquiry_links_one_target`.
F5 (FE) - the PO picker footer counted untickable taken rows in its denominator. F3-FE (FE) -
the schedule legend's grey label widened from "Another SPO" to "Taken elsewhere" to match F3.

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
- **Legend** (captain's Lavish note 3 Sep): a one-line legend under the matrix, two swatches
  with their words - blue "This SPO", grey "Taken elsewhere" - rendered only in schedule view.
  A colour with no key is an explanation the reader has to guess, which is worse than a
  sentence; two swatches are the sentence. (Review round: worded "Another SPO" at S4 time,
  before F3 widened the grey state to cover a plain PO placement too.)

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
  lines whose `source_ref.pulls` name the PO line (the same FACT
  `PurchaseOrderService._allocations_for` reads for the PO panel, but as its own query -
  `_spo_pulls_by_po_line` - copied with the reason in its docstring: that read also fetches
  the LANDING, packing list, warehouses, arrival date, this one does not, so folding it in
  was not a clean drop-in). A PO line to this supplier
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

### S7. The other side of the loop: what the PO and the SO say after Create SPO (BE + FE)

Captain's Lavish note 3 Sep: "after I create SPO, I need visibility that this PO is used to
supply this SPO, how many left, how many supplied, from the PO form; same for SO."

- **PO form: already there.** `PurchaseOrderAllocations` on the PO detail prints per line
  Outstanding / Allocated / Free and every placement, an SPO one as `SPO-… qty` with its
  packing list (`kind: 'spo'`, `spo_number`, `packing_list`, from
  `PurchaseOrderService._allocations_for`). Nothing to build; S6's evidence run opens the
  source PO after Create SPO and screenshots the block. One wording check: the PO line's
  Received figure includes the SPO pull (that is how `create` records it), so the panel
  must say "Pulled to SPO N" on the placement, not leave the reader to infer it from
  Received.
- **Project SO line: already there.** The tick is the ORDER BACK order-inquiry row on the
  line; `create` writes `OrderInquiryLink` rows; the SCM sales-order detail's "Linked to"
  column (`linked_to`, AC-I9) prints `SPO-… <warehouse> <qty> due <date>` off that link,
  and the order-inquiry worklist and the PO occupancy panel read the same reader. So yes:
  we cover the OI row, which is how the project SO line is reached (OI = demand), and the
  project SO shows it.
- **Retail SO line: NOT there.** The retail tick is recorded only in the SPO line's
  `source_ref.so_coverage`; nothing on the SO side reads it, so a retail line covered by an
  SPO reads "-" in Linked to. Build:
  - `spo_conversion_service.coverage_for_so_lines(db, so_line_ids) -> dict[so_line_id,
    list[dict]]`: for every `crm_spo` PO line whose `source_ref.so_coverage` names one of the
    lines, one entry `{kind: 'spo', document: <SPO number>, qty, location: <allocation
    warehouse code or None>, expected_date: <shipment ETA or None>, line_label: None}` -
    the `SalesOrderLineLink` shape. Shared with S5's `taken_by` read (one query, both
    callers).
  - `sales_order_service` line builder: for a line with no inquiry row, `linked_to` =
    that list when non-empty, else `None` as today. A line with an inquiry row keeps the
    OI links and appends the SPO coverage entries after them.
  - FE: no change; the "Linked to" cell already renders the shape.
  - Pytest first (`tests/scm/test_sales_order_detail_links.py` or the existing SO detail
    test file): retail line covered by one SPO reads one `spo` link with the SPO number
    and qty; two containers = two links; after `unwind` the line reads `None` again.
    Route test asserts the field through the API.

### S6. Tests, browser evidence, review

- Vitest: `SpoPlannerTable.test.tsx` (no subtitle, no partly-covered sentence, toolbar
  groups, View labels, no row description), `PlanRowDialog.test.tsx` (description rule,
  picker headers, filter narrows rows and keeps ticks, taken rows), matrix table test (tint
  classes, click opens dialog).
- agent-browser evidence run on :3160 via the sidebar: Procurement → Packing lists → a draft
  shipment → SPO planner; both views; open a cell; filter in the SO picker; screenshot each.
- Evidence run also opens the source PO (Outstanding / Allocated / placements) and the SCM
  sales order (Linked to) after Create SPO, for S7.
- Full `npm run test`, whole-frontend `npx tsc --noEmit`, `pytest tests/scm/test_spo_planner_selection.py tests/scm/test_spo_conversion.py`, `alembic heads` (no migration in this batch).
- Opus review, then ONE PR after the lightbox PR merges.

## 3. Not in scope

- Week granularity toggle on the schedule (still the follow-up the doctrine plan named).
- Filtering the SO picker by date range (the schedule click answers that).
- Any change to the cascade, default ticks, or what `create` writes. Netting stays the rule;
  S5 only makes it visible.
- The SPO history dialog (lightbox S4 covers it).

## 4. Order

S1 → S2 → S3 → S4 → S5 (BE test-first, then FE) → S7 (BE test-first) → S6. One coder at a time in this worktree.

## 5. Round 2 (captain, 3 Sep late, on :3160 after S1-S7)

**Status:** APPROVED by the captain 3 Sep late ("ok good to go" on Lavish, after rulings: cap removed, lightbox not card, one Project group). Measured facts first, then slices R1-R5.

| Saw | Measured cause |
| --- | --- |
| "SPO already created" is a badge list; one SPO per container; no link to the SPO; cannot recall the plan | `create` refuses a second run with 409 `already_converted` (`spo_conversion_service.py:1567`); `_existing_spos` returns `purchase_order_id` but the FE prints a `Badge`, not a link (`SpoPlannerTable.tsx:945`). The plan (pulls, SO cover) is on the SPO line's `source_ref` and nothing renders it. |
| Qty input "choppy" | Input is clamped live to PO cover (`renderQtyCell` `Math.min`), every keystroke re-runs the tick walk and the red `overTicked` banner names every starved SO while typing, and it disables Create SPO. |
| SO367360 reads Retail, the SO list says Project | Planner `kind` = where the row comes from: `project` = an order-inquiry row, `retail` = any sales-order-book line (`_retail_coverage`). The list's Type pill is `sales_orders.demand_class`. The two words collide. |
| SO detail shows no SPO after Create | Image taken before Create; the `Linked to` column exists (S7) but sits last, off-screen at 1280. |
| PO "Allocated to" overload | One block per PO LINE with three figures, "Dedicated to" chips, and a six-column table whose "Needed at" for an SPO row prints the warehouse split (`PurchaseOrderAllocations.tsx:168-177`). |

### R1. Many SPOs per container, listed as a grid, each a link, each with its plan

- `suggest` no longer flips to `already_converted`. It returns `existing_spos[]` (DataGrid rows: SPO number, supplier, lines, qty, created at, status pill, Delete) AND the planner for the **remainder**: per line `packed - sum(qty already on this container's SPO lines for that shipment line)` via `ShipmentLineSpoLink`. A line with no remainder renders qty 0, disabled, "Done".
- `create` refuses (422 `nothing_left`) only when no line has a remainder. `unwind(shipment_id, purchase_order_id)` deletes ONE SPO; the row's Delete calls it (confirm dialog, as today).
- SPO number links to `/scm/purchase-orders/{purchase_order_id}`. `PurchaseOrderDetail` gains a **Plan** card when `source_system == 'crm_spo'`: per SPO line, "Pulled from" (PO number, qty) and "Covers" (SO number, customer, qty, warehouse) read off `source_ref` through one new reader `spo_conversion_service.plan_of(db, purchase_order_id)`.
- Route: `DELETE /inbound-shipments/{id}/spo?purchase_order_id=` (absent = every SPO, today's behaviour kept for the old callers/tests).

### R2. Quantity is free to type; the warning is one dialog at Create

- Input accepts any whole number; no live clamp, no live red banner, Create SPO enabled whenever any line has qty > 0 (split mismatch still blocks, it is arithmetic).
- Create SPO opens **Review before creating**: per line, "Asked N, POs cover M, SPO will be M" when N > M; "Ticked SOs ask X, this SPO covers Y" when over-ticked; "No location" when no split. Confirm sends today's payload. The server caps at PO cover exactly as it does now (doctrine: an SPO only pulls from a PO; unchanged).
- **Captain's ruling (Lavish, 3 Sep late): remove the cap too.** `create` takes `need = min(requested,
  packed)`; the PO cascade pulls what open POs cover and the rest of the line is written WITHOUT a
  PO pull (`source_ref.pulls` names only the covered part; `no_po_qty` = the rest). A line with no
  open PO at all is convertible (its `reason` stays as information, `cannot_convert` is only true
  for a line with no supplier). `suggested_qty` stays the PO-covered figure as the DEFAULT. The
  review dialog says "Asked 500, POs cover 409, 91 without PO backing". Tests
  `test_create_refuses_when_nothing_ticked_has_a_po_behind_it` and `test_suggest_with_no_open_po_at_all_cannot_convert_and_names_why`
  flip to the new rule (kept as tests of the new behaviour, not deleted).

### R3. Class = the sales order's own class

- Coverage rows carry `demand_class` (`sales_orders.demand_class`); the Class column prints it (Project / Retail / Unclassified) with the SO list's own `demandClassBadge`. An order-inquiry row prints "Project · inquiry".
- Internal `kind` (inquiry vs book line) is unchanged; it decides where the link is written.
- **Captain's ruling (3 Sep late):** two groups. Project demand = inquiry rows AND Project-type SO lines
  merged by delivery date (an inquiry row is a project SO line that went through the inquiry flow, so
  they are one group, not two); then Retail by delivery date. A project SO line that already has an
  inquiry row appears once, as the inquiry row (that is where the link is written).

### R4. SO detail: Linked to beside Outstanding

- `SalesOrderDetail` lines: `linked_to` column moves to sit after `outstanding_qty`; default visible.

### R5. Placements as a lightbox off the lines grid, PO and SO alike

**Captain's ruling (Lavish, 3 Sep late):** not a card under the grid - "click the line in the lines table
and open the lightbox popup that shows this allocation", and "apply this for SO also".

- **PO detail** `PurchaseOrderDetail` lines grid: new column **Placed** = sum of placements on the
  line (SPO pulls + inquiry links + dedications), a `PlanNumberButton`; click opens
  `PlanRowDialog kind='placements'` titled `Placed on · <code>`; body = one DataGrid: Placed on
  (SPO pill + number link / inquiry number / Dedicated pill), Document (packing list or sales order,
  link), Customer, Qty, Lands at, ETA; footer `Outstanding N · Placed M · Free F`. Data =
  `PurchaseOrderService._allocations_for` as today (already on the PO payload). The
  `PurchaseOrderAllocations` card is removed.
- **SO detail** `SalesOrderDetail` lines grid: the `Linked to` column becomes **Linked** = sum of
  link qty as a `PlanNumberButton` (dash when none); click opens `PlanRowDialog kind='links'`
  titled `Linked to · <code>`; body = DataGrid: Kind pill (SPO / PO), Document (link), Qty, Lands at,
  ETA, Late; data = the line's existing `linked_to` array. Inline multi-link text is gone.
- Both dialogs are the shared `PlanRowDialog` shell (S2 description rule, no context string).

Superseded proposal A/B text kept below for the record.

#### (superseded) PO "Allocated to": one flat table

Proposal A (recommended): one DataGrid for the whole PO. Columns: **Line** (product code · location · delivery date), **Placed on** (SPO pill + number as a link, or inquiry number), **Document** (packing list or sales order, link), **Customer**, **Qty**, **Lands at** (warehouse split, `BRW-BB 135`), **ETA**. Group header row per PO line: `Outstanding 209 · Placed 135 · Free 74`. "Dedicated to" becomes rows of kind **Dedicated** (SO number, qty) in the same table. "Needed at" column is gone (it was the split).
Proposal B: keep the blocks, drop the three-figure line to the group row, drop "Dedicated to" chips into rows, fix the SPO row to `Lands at`.
Both keep `PurchaseOrderService._allocations_for` as the source; FE only.

Order: R3, R4 → R2 → R5 → R1. R3 order ruled (one Project group).
