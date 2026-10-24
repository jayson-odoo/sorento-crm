# PLAN: order inquiry sheet as a migration tool

Status: MERGED 14 Sep 2026, PR #875 (squash ae0831776), issue #873 closed.
Browser evidence stays in `documentation/plans/scm/evidence/oi-sheet-migration/`.
Owner check before the first prod upload: only purchasing / admin roles hold
scm.reorder.run (security review SF3).

Owner ruling, 13 Sep 2026: "we don't need to create sales orders, the sales
orders are created, so we need to create order inquiries instead ... that
match with the SO line with the quantity, SO number and location, and we also
need to do the PO/SPO pairing, this is like our migration tool for the user's
excel order inquiries, doesn't matter order back or not, the PO/SPO and SO are
real time integrated with autocount already."

UAC: `scm-oi-sheet-migration-acceptance-criteria.md` (journey at the top).

## 0. What was measured before writing this

Read against the local 8 Sep prod copy and the code on `main` at `c385da410`.

**What the upload on `/scm/reorder` does today** (`app/services/
project_order_inquiry_import_service.py`, `apply()`):

| step | writes | kept? |
| --- | --- | --- |
| `_create_orders` | `sales_orders` + lines for SO numbers not in the book, owned by the sheet (`source_system = scm_order_inquiry`); refresh / withdraw on re-upload | **dropped** |
| location loop | `sales_order_lines.warehouse_id` from the sheet | **dropped** |
| claim loop | `scm.order_link_claim` (source `order_inquiry`) per cited PO, then `order_link_service.resolve()` | **dropped** (the link write makes its own claim) |
| `_raise_rows` | `projects.order_inquiry_rows`, **ORDER BACK rows only**, `so_line_id` only when the book holds an UNDATED open line | **rewritten**: every row, against the real line |
| cascade | `auto_place_for_products(row_ids=raised, trigger="order_inquiry_form")`, cited documents first, then any fitting line | **replaced** by explicit pairing to the cited document only |

So a sheet full of dated rows raised nothing on the Order Inquiries page, and
that is the "macam didn't link" the owner saw on 13 Sep.

**The book is AutoCount's now.** On the prod copy `sales_orders.source_system`:
`autocount` 75,600, `scm_upload` 10,730, `scm_so_history` 950,
`scm_order_inquiry` 12. Open lines: 34,572 carry a warehouse, 307 do not. Open
project-class orders: 902. Existing inquiry rows: 57 (55 distinct lines, 13
inquiries), 48 links. Claims: `order_inquiry` 2,101 resolved / 1,081 open,
`po_history` 13,062 / 20,173.

**Primitives that already exist and are reused, not rebuilt:**

* `ProjectSOAdoptionService.adopt(core_so_id, actor)` - get-or-create the
  planning mirror (`ProjectSalesOrder` + `ProjectSalesOrderLine` per open core
  line, `core_sales_order_line_id` set). Refuses with codes
  `sales_order_not_project_class`, `sales_order_not_open`,
  `sales_order_nothing_outstanding`. The migration needs the first refusal
  and neither of the others, and needs closed lines mirrored, so it gets a
  sibling `adopt_for_migration` built from the same `_insert_record` and
  `_mirror` pieces (section 2).
* `is_open_demand()` / `demand_qty()` (`app/services/scm/demand.py`) - the one
  open-line predicate and outstanding quantity.
* `ProjectOrderInquiryService._write_link(row, candidate, qty,
  actor_user_id=...)` - the ONE writer of an `OrderInquiryLink`, its audit
  claim (`claim_placed_on_po`) and the row's note stamp. The public
  `place_on_po_allocations` wraps it behind an open-line gate this migration
  must not have (D8).
* `ProjectOrderInquiryService._linked_by_target()` - what every link already
  claims per PO line / SPO allocation; the capacity tally.
* `ProjectOrderInquiryService.refresh_link_state(rows)` - the one writer of
  `state` / `po_ref` / `po_line_id` / `spo_ref` from a row's links.
* `order_link_service._claim_rows(db, so_line_ids=...)` - every RESOLVED
  claim on a core sales order line as `{claim_id, target_id, po_number,
  source, so_line_id, ...}`; `target_id` is the PO line or the SPO
  allocation. The AutoCount ingest (`document_ingest_service`,
  `shipping_order_ingest_service`) writes these through
  `write_line_ref_claims` (exact `from_so_line_ref`) and
  `write_claims_for_lines` (`from_so_numbers`), source `autocount`.
* `order_link_service._purchase_side(db, po_numbers)` - `(po_number,
  item_code)` to `("po_line_id" | "spo_allocation_id", row_id)` by the
  number's own prefix.
* The reader (`project_order_inquiry_reader.py`) - untouched. It already
  yields `so_number, item_code, qty, delivery_date, location, po_numbers,
  not_ordered, order_back, remark, sheet, source_row`.
* The job machinery (`_run_scm_upload_job`, `ImportOutcome`, the upload
  drawer) - untouched. Route, permission (`scm.reorder.run`), job type
  (`order_inquiry_import`) and queue are unchanged.

## 1. Decisions (grilled 13 Sep 2026)

| # | question | ruling |
| --- | --- | --- |
| D1 | line match | same SO + item, sheet qty at most the line's ORDERED qty less what earlier rows of the file took (so the sheet may split one line), location equal; a line with no warehouse accepts any location. Line status is ignored |
| D2 | line already has an inquiry row | skip the sheet row, count `rows_already_raised`, touch nothing |
| D3 | cited PO/SPO line short | link what fits (`partly_linked`), report the rest; a missing document, or one with no line for the item or no capacity, leaves the row raised unlinked with its citation. Capacity = ordered less other links, so a closed, fully received line links like an open one |
| D8 | history (owner, Lavish note 13 Sep) | "those historical sales orders won't have outstanding already ... most likely those old order inquiries are linked to sales orders that are completed, but we still need to migrate those in." Closed sales orders, delivered lines and received PO lines all migrate. Only the project-class check refuses an order |
| D4 | sales order creation and the location write | both dropped; AutoCount owns them |
| D5 | rows neither AutoCount nor the sheet pairs | raised unlinked with NO cascade over "whatever fits". Auto-link stays the worklist's button |
| D10 | SO -> PO -> SPO chain (owner question 4) | The link lands on the SPO. A direct SO -> SPO claim is taken first; otherwise an AutoCount PO pairing is followed through `SPOAllocation.from_po_number` to that PO's SPO allocations before the PO line itself. The worklist already prints an SPO link with its source PO |
| D9 | AutoCount-stated pairing is the source of truth (owner, Lavish notes 2 and 3, 13 Sep) | "most likely those order inquiries from historical data has sales order line linked to the purchase order in the autocount data already ... even for those closed PO / SPO we also need to find the link based on the linkage specified in autocount data ingested to us." And: "we don't trust the remark column in the sheet, we can refer but the source of truth is the autocount linkage." The ingest already writes that linkage as RESOLVED `order_link_claim` rows (source `autocount`, from `from_so_line_ref` and `from_so_numbers`, on PO lines AND SPO allocations). The importer reads those claims for the row's core line FIRST and links to their targets, SPO allocation before PO line. The sheet's remark is tried only for need AutoCount leaves, and is kept on the row as `cited_document` for reference |
| D6 | verb | `ORDER_BACK` when the date cell says so, `ORDER` otherwise; both raised |
| D7 | duplicate rows within one file | identical `(SO, item, qty, date, location, remark)` collapse to one row; the second carries outcome `unchanged` / `restates_an_instalment` |

## 2. Design, S1 (backend)

One module, three functions, plus one new method on the adoption service.
No new table, no migration.

```
read_order_inquiry(file)            # unchanged reader
_plan(db, parsed) -> Plan           # pure: match every row, decide raise/skip/report
apply(db, file, actor, outcome)     # _plan + write
preview(db, file)                   # _plan + counts, writes nothing
```

`Plan` holds, per sheet row: `core_line` (SalesOrderLine or None), `reason`
when None, `already_raised` flag, `cited` (ordered list of `(doc_number,
target column, target id)` or None per document). Computed once so preview
and apply cannot disagree.

**Match (D1, D8).** Group rows by SO number. For each SO:

1. `sales_orders` by `so_number` (company scoped). Missing: every row
   `order_not_found`, number under `sales_orders_not_found`.
2. Lines: EVERY `SalesOrderLine` of the order, any status, joined to
   `Product.product_code` and `Warehouse.warehouse_code`.
3. For each row in sheet order: candidates = lines with the row's item code,
   `warehouse_code` equal to the sheet location (upper, stripped) or line
   warehouse NULL, and `qty_ordered - taken[line] >= row.qty`. Pick the one
   whose `required_date == row.delivery_date`, else `line_status == "open"`
   first, else earliest `required_date` (NULLs last), else `created_at`.
   `taken[line] += row.qty`. No candidate: reason is the FIRST failing
   filter in the order item -> location -> qty (`no_line_for_item`,
   `location_differs`, `qty_exceeds_ordered`).

**Adopt (D8).** `ProjectSOAdoptionService` gains one method,
`adopt_for_migration(core_id, actor)`: get-or-create the planning record
exactly as `adopt` does, but the only refusal kept is
`sales_order_not_project_class` (`_assert_plannable`'s open and outstanding
checks are skipped), and it mirrors EVERY core line the record does not yet
carry, closed ones included, through the existing `_mirror`. `adopt` and
`mirror_missing_lines` are untouched, so the board's own gate stays as it
is. On refusal every row of that SO is `order_not_plannable` with the code,
and the SO goes under `orders_not_plannable`. Mirror line =
`ProjectSalesOrderLine` where `core_sales_order_line_id == core_line.id`.

**Skip (D2).** Any `OrderInquiryRow` with `so_line_id == mirror.id` and
`state != cancelled` marks the sheet row `already_raised` (outcome `skipped`,
code `already_raised`). Nothing on that row or its links is touched.

**Raise.** Header: the SO's `OrderInquiry` with `amendment_id IS NULL`, or
create one exactly as `_raise_rows` does today (uploader stamped only on a
header this upload creates). Row: `company_id`, `order_inquiry_id`,
`so_line_id = mirror.id`, `item_code`, `qty = row.qty`, `delivery_date =
row.delivery_date or core_line.required_date`, `stock_location =
row.location or line warehouse code`, `verb` per D6, `cited_document =
first cited number or None`, `note = remark or None`, `state = raised`,
`ack_state = acknowledged`, `acknowledged_by = actor`, `acknowledged_at =
now`. `note` is prefixed `Migrated from order inquiry sheet <file name>`
(AC-S1-28). Flush before pairing so the row id exists.

**Pair, source 1: what AutoCount states (D9).** `need = row.qty`.
`order_link_service._claim_rows(db, so_line_ids=[core_line.id])`, keep
`source in {autocount, po_history, po_upload}` (never `order_inquiry`,
`crm_supply`, `planner`), order SPO allocation targets before PO line
targets, then `claimed_at`. For each target while `need > 0`: capacity =
`qty_ordered` (PO line) or `allocated_quantity` (SPO allocation) less that
target's total in `ProjectOrderInquiryService._linked_by_target()`; zero or
less -> skip; else `qty = min(need, capacity)`, one `_write_link(row,
candidate, qty, actor_user_id=actor, auto_trigger="autocount linkage")`
call with a candidate dict the importer builds (`document`,
`supplier_name`, `expected_date`, `po_line_id`, `spo_allocation_id`), then
`need -= qty`. A row that gained a link here counts under
`links_from_autocount`. The prod copy the plan was measured on predates the
ingest's linkage widen (migration 493), so the volume could not be measured
locally; on prod the `autocount` source exists and is what this reads.

**Follow the chain SO -> PO -> SPO (D10, owner question 4, 13 Sep: "if the
order inquiry is linked to a SO line that is linked to PO that is linked to
SPO line, will it appear in the UI?").** Yes, and the link lands on the SPO
so the worklist shows it. Two ways the chain is known, both handled:

1. The SPO feed states the SO line itself (`from_so_line_ref` on the
   allocation, contract 2.2): the ingest already wrote a direct SO -> SPO
   claim, and source 1 above takes it first (SPO before PO).
2. The SPO feed states only the PO it came from (`SPOAllocation.
   from_po_number`): before linking an AutoCount PO-line pairing, the
   importer looks for `spo_allocations` with `from_po_number == that PO
   number` and the row's `product_id`, ordered by `spo_number`, and links
   those allocations first (same capacity rule); the PO line takes only the
   need they leave. An allocation already linked in step 1 is skipped.

The worklist's `links_for_rows` already prints an SPO link with its
`source_po_number` off `from_po_number`, so no reader changes. Sorento-raised
SPOs (`spo_allocations.po_line_id` / `source_ref` pulls) are the CRM's own
conversions, not AutoCount's record, and are out of this migration's scope.

**Pair, source 2: the sheet's remark, reference only (D3, D8).** Still
`need > 0` and the remark cites documents (`po_numbers`, not `not_ordered`):
resolve each cited number with `_purchase_side` narrowed to the row's item
code (it already answers `("po_line_id" | "spo_allocation_id", id)` by the
number's prefix and does not filter on status). A target AutoCount already
linked above is skipped. Same capacity rule, same `_write_link` call (no
`auto_trigger`, it is the operator's own citation), in citation order. A
number that resolves to nothing, or to a target with no capacity, goes under
`documents_not_linkable`. The first cited number is stored as the row's
`cited_document` whether or not it was linked, so the worklist shows where
the sheet and the book disagree.

After both sources: `refresh_link_state([row])` sets `placed` /
`partly_linked`. `need > 0` with at least one link -> `links_partial += 1`;
any link -> `links_written += 1`.

Why `_write_link` and not `place_on_po_allocations`: the public method
refuses a closed line and reads capacity from `_candidates_for_row`, which
lists open lines only. History is closed lines. `_write_link` is the one
writer of the link and its claim and audit stamp, so calling it directly
keeps one link-writing path; the only thing skipped is the open-line gate,
which is exactly D8. `_invalidate_link_cache()` is called by `_write_link`,
so the capacity tally re-reads after each write.

**Actor.** The uploader (`user_id` on the job). `_link_actor`'s act-as
fallback is kept for an unattended run; with no actor at all the pairing
step is skipped and `link_error` is NOT a result key any more - the rows are
raised and `documents_not_linkable` lists every citation.

**Commit shape.** Same as today: one transaction owned by
`_run_scm_upload_job`. The sheet is hundreds of rows, not the 82k-row book,
so per-batch commits are not copied here (PRINCIPLES: copy a mechanism only
with the justification that earned it).

**Removed code:** `_create_orders`, `_instalments` collapse and everything
that fed it (`_summarise`'s instalment counts, `_so_lines`, `_order_back_lines`,
`_restate`, the location loop, the claim loop, the post-raise cascade,
`_link_actor`'s use by the cascade). `SOURCE_SYSTEM = "scm_order_inquiry"`
stays defined: raw SQL in `scm/demand.py` and migration 346 reference it and
the 12 existing sheet-owned orders keep their marker.

**Kept from `_create_orders` (ruling 14 Sep, AC-S1-37):** the one header
stamp it applied to EXISTING orders as well as created ones, project-label
rule 1 (`apply_project_label(order, label_from_inquiry_cell(row.project),
"inquiry")`, `PLAN-so-project-label.md`). It runs once per sales order the
sheet names and the CRM holds, before the rows are raised. Any other
per-order stamp `_create_orders` applied to an existing order (a
`demand_origin` or similar) is kept the same way; creation, refresh and
withdrawal are what go.

**Coder rulings folded in (14 Sep, after S1 went green bar two):**

* AC-S1-29 as first written was unsatisfiable: `scm.committed_v`'s project
  leg (migration 424) counts every raised / partly_linked inquiry row with
  no supply decision, whatever its core line's status, so a migrated history
  row would have inflated project demand and bought goods for delivered
  orders. Ruling: no migration; a row whose matched line is not
  `is_open_demand()` is raised, linked, state-refreshed, then set
  `actioned` by the uploader. The view ignores `actioned`; the worklist still
  shows the row and its links under the actioned filter.
* D7 IS built (AC-S1-38): exact-duplicate rows within one upload collapse,
  because the customer's workbook restates rows across tabs and without it
  every restatement would either raise twice or take `qty_exceeds_ordered`.
  The coder writes this one test itself, a recorded deviation from
  tester-first (the tester's worktree was already reclaimed).
* Retired with the code, beyond the four the plan named:
  `tests/scm/test_order_link_both_ways.py` (whole file; asserts sales-order
  creation, warehouse writes and importer-written claims; closes issue
  #869's collision too) and in `tests/scm/test_order_inquiry_routes.py` the
  two cases asserting `po_claims` / `claims_written` / `links`.
  `test_open_claims_are_reportable_over_http` seeds its own claim row
  instead of relying on the importer, or is retired if that is not a small
  change.
* `test_adopt_for_migration_mirrors_every_line_and_keeps_one_refusal` reads
  `refused.value.code`; `AppException` carries the code in
  `detail["code"]` like every other test. Tester defect; the coder fixes
  that one line and reports it.
* `ALSO_CITED_PREFIX` stays defined (read at call time by
  `ProjectOrderInquiryService._also_cited`); nothing writes it any more.
* The Phase 1 "mock" was a type-shape mock over the real URLs, so S2's swap
  is a no-op; the browser run (AC-S2-6) is the end-of-lane verification.

**Noted in the browser run, recorded not fixed (14 Sep):**

* The worklist has no column naming the linked document; it is read in the
  Backing documents dialog. Pre-existing surface, not this lane's.
* `_write_link` stamps `actioned_by` / `actioned_at` on a PLACED row too, not
  only on the history rows this lane actions. Pre-existing manual-link
  behaviour.
* Confirm is enabled before the first preview has returned. Pre-existing
  `useTwoStepUpload` behaviour; AC-S2-4 is scoped to what the preview state
  says once there is one.

**Code review adjudication (14 Sep, Opus reviewer, ready, kill tests
AC-S1-10 / 30 / 29 all red):**

| finding | ruling |
| --- | --- |
| 1 `_target_facts` resolves retired SPO allocations | fix: `spo_supply.visible_line_clauses()` on the allocation filter |
| 2, 3 D7 key ignores `po_numbers` and `order_back` | fix: both join the key |
| 4 `adopt_for_migration` widens a board-owned record with every closed line | fix: mirror open lines plus matched lines on a fresh record; only missing matched lines on an existing one (AC-S1-26 amended); coder writes the test |
| 5 dialog reason wording contradicts the code and the job page | fix: same sentences as `import_outcome_codes.LABELS` |
| 6 "Documents found" tile counts rows | fix: relabel "Rows linked" (AC-S2-1 amended) |
| 7 job result-key test is directional | fix: equality, stale sentence gone |
| 8 AC-S1-29 state half untested | already landed in 6b14dfedb after the reviewer's checkout |
| 9 a skipped row consumes the ledger | fix: consult already-raised before `taken` grows |
| 10 refusal after plan mis-reported, capacity not released | accepted as is; unreachable while `_plan` and adoption agree on the class check |
| 11 capped list headings print the sample length | fix: no count on those two headings; NO new count keys (would add surface for nothing) |
| 12 plan status | captain, at PR time |

**Security review adjudication (14 Sep, Opus security-reviewer, no
blockers):**

| finding | ruling |
| --- | --- |
| SF1 header stamps hit refused orders too | fix: stamp only non-refused orders with a raisable row (AC-S1-39) |
| SF2 preview hides adoption / mirroring / stamping | fix: `orders_adopted` + `orders_stamped` on the result and a seventh tile (AC-S1-22, AC-S2-8). Mirror-line count not added: noise, nobody acts on it |
| SF3 `scm.reorder.run` now adopts, acknowledges and actions | no code change. The sheet upload IS purchasing's migration tool and the old importer already raised acknowledged rows and placed links. Recorded here and in the PR; the owner confirms on prod that only purchasing / admin roles hold `scm.reorder.run` before the first real upload |
| N1 raw actor on rows | fix: refuse an apply with no attributable actor (AC-S1-42) |
| N2 negative qty frees ledger capacity | fix (AC-S1-40) |
| N3 over-long location aborts the job | fix (AC-S1-41) |
| N4 preview as an intra-tenant quantity oracle | accepted; same company, behind the operator grant |
| N5 uncapped label cell, quadratic regex | fix (AC-S1-44) |
| N6 no cross-company test | fix: coder writes AC-S1-43's test (recorded deviation) |
| N7 job-scope fallback to all companies | informational, unreachable from this route, pre-existing |

**Tester rulings folded in (14 Sep):** result = 15 keys (`ok`, `problems`
plus the 13); no `missing_columns` key; `apply(..., file_name=)` for the
note stamp; `_claim_rows` gains `claimed_at`. In
`tests/scm/test_scm_import_tasks.py` the three tests asserting retired
behaviour (`test_a_row_restating_an_instalment_is_counted_not_lost`,
`test_a_withdrawn_instalment_is_recorded_and_counted_into_the_total`,
`test_a_document_another_feed_owns_is_left_alone_and_every_row_says_so`)
are retired with the code, and
`test_the_inquiry_sheet_records_an_outcome_for_every_row` moves its expected
codes to the new matcher's (`order_not_found` for an unseeded sales order).
The coder makes exactly those four edits and reports them; no other test
changes without a report.

**Worker note.** The worker imports the service inside the task function, so
the running worker must be restarted to pick the new code up.

## 3. Design, S2 (frontend)

`app/(protected)/scm/reorder/components/OrderInquiryUploadDialog.tsx` and
`services/orderInquiryService.ts` only.

* `OrderInquiryPreview` type = the AC-S1-22 keys. Retired keys removed.
* `InquirySummary`: six `CountTile`s (Rows, Will raise, Already raised, No SO
  line, Documents found, Documents not found), then three `ChipList`s:
  "Sales orders not in the CRM", "Documents we could not link", "Rows with
  no matching line" (entries formatted `SO · item · qty · reason`; reason
  printed in words: "no open line for this item", "location differs",
  "quantity exceeds outstanding"). The existing `ChipList` cap stays.
* Confirm enabled when `ok && rows_raised > 0`.
* The `sheets read / skipped` line and the `Problems` block stay as they are.
* No motion added (AC-S2-7).

The vitest for the dialog updates its fixture to the new shape; the service
test asserts the two URLs and the multipart field, as today.

## 4. Tests (captain's list for the tester)

Backend, `tests/test_project_order_inquiry_import_migration.py` on the
Postgres fixture (`tests/_pg_fixture.py`), seeding its own SO, product,
warehouse, PO/SPO chain (CI DB has no data):

* AC-S1-1 `test_row_raises_against_matching_line` - one row, one open line, same location, row raised with mirror `so_line_id`, qty, date, location.
* AC-S1-2 `test_two_rows_split_one_line` - 30 + 20 against a 50 line: two rows, both on that line.
* AC-S1-3 `test_line_without_warehouse_accepts_location` - line warehouse NULL, row at BRW-IB: raised, `stock_location == "BRW-IB"`.
* AC-S1-4 `test_location_mismatch_reports_not_found` - line at BRW, row at BRW-IB: nothing raised, reason `location_differs`.
* AC-S1-5 `test_qty_over_ordered_reports_not_found` - 60 against a 50 line: reason `qty_exceeds_ordered`.
* AC-S1-6 `test_unknown_so_creates_nothing` - `sales_orders` count unchanged, number listed.
* AC-S1-7 `test_retail_order_not_plannable` - retail-class SO: `orders_not_plannable` carries the code, nothing raised; a CLOSED project-class SO is adopted and raised.
* AC-S1-8 `test_prefers_line_with_same_required_date` - two lines 1 Oct / 15 Oct, row dated 15 Oct lands on the 15 Oct line; undated row prefers the open line over the closed one.
* AC-S1-9 `test_verb_from_date_cell` - `ORDER BACK` cell -> `ORDER_BACK`; dated -> `ORDER`.
* AC-S1-10 `test_line_with_existing_row_is_skipped` - seed a board row on the mirror line: `rows_already_raised == 1`, row count unchanged, its link untouched.
* AC-S1-11 `test_second_apply_is_a_noop` - apply twice: second run `rows_raised == 0`, `rows_already_raised == first.rows_raised`.
* AC-S1-12 `test_cited_po_is_linked_in_full` - link qty == row qty, `linked_by == actor`, row state `placed`.
* AC-S1-13 `test_cited_spo_is_linked` - `spo_allocation_id` set, verb `ORDER`.
* AC-S1-14 `test_short_po_line_links_partial` - line remaining 10, row 30: link 10, state `partly_linked`, `links_partial == 1`.
* AC-S1-15 `test_unknown_document_leaves_row_unlinked` - no link, `cited_document` kept, number under `documents_not_linkable`.
* AC-S1-16 `test_two_cited_documents_in_order` - `A & B`: A takes its remaining, B takes the rest.
* AC-S1-17 `test_order_remark_raises_unlinked_no_cascade` - remark `ORDER`, no claim on the core line, a fitting open PO line present: no link written.
* AC-S1-18 `test_dedicated_line_still_links_when_cited` - another SO's resolved claim on the line: link still written.
* AC-S1-19 `test_no_sales_order_writes` - assert `sales_orders` / `sales_order_lines` counts unchanged across every fixture above (one parametrised test).
* AC-S1-20 `test_warehouse_id_untouched` - line warehouse NULL stays NULL after apply.
* AC-S1-21 `test_no_direct_claim_rows` - the only `order_link_claim` rows after apply are the link write's (`source == "order_inquiry"`, one per link).
* AC-S1-22 `test_result_keys_exact` - `set(result) == {...}`.
* AC-S1-23 `test_one_outcome_per_row` - outcomes count == sheet rows, codes as listed.
* AC-S1-24 `test_preview_writes_nothing_and_matches_apply` - preview counts == apply counts; row/link counts unchanged after preview.
* AC-S1-25 `test_missing_header_refused` - `ok False`, `missing_columns`.
* AC-S1-26 `test_closed_delivered_order_migrates` - SO status closed, line delivered in full: planning record created with the closed line mirrored (`qty` = ordered), row raised on it, core untouched.
* AC-S1-27 `test_closed_received_po_line_links` - PO line closed, `qty_received == qty_ordered`: link written for min(row qty, ordered less other links).
* AC-S1-28 `test_row_note_carries_migration_stamp` - note starts with `Migrated from order inquiry sheet <file>`.
* AC-S1-29 `test_closed_line_row_not_open_demand` - `scm.committed_v` total for the product unchanged after apply.
* AC-S1-30 `test_autocount_claim_pairs_row_first` - seed a resolved `autocount` claim (so_line_id + po_line_id) on the core line, sheet row with empty remark: link written to that PO line, note carries `auto: autocount linkage`.
* AC-S1-31 `test_autocount_first_then_citation_fills_rest` - claim target covers 20 of 30, citation covers the remaining 10: two links, row `placed`, the AutoCount link first.
* AC-S1-31b `test_autocount_wins_over_remark` - claim says PO A, remark says PO B, A has capacity for the whole row: one link to A, none to B, `cited_document == B`.
* AC-S1-32 `test_autocount_spo_before_po` - one claim to an SPO allocation and one to a PO line on the same core line: the SPO allocation is linked first.
* AC-S1-33 `test_own_and_crm_claims_ignored` - claims with source `order_inquiry` / `crm_supply` / `planner` on the core line: no link written from them.
* AC-S1-35 `test_po_pairing_follows_from_po_number_to_spo` - claim SO line -> PO line; an SPO allocation for the product with `from_po_number` = that PO: link to the SPO allocation, PO line only for the remainder.
* AC-S1-36 `test_direct_spo_claim_wins_over_chain` - both a direct SO -> SPO claim and the PO chain name the same allocation: exactly one link to it.
* AC-S1-34 `test_links_from_autocount_counted` - `links_from_autocount == 1` for the AC-S1-30 fixture, `0` for a fully cited row.

Retired with the code they tested: `test_project_order_inquiry_import_creates_demand.py`,
`test_project_order_inquiry_import_cs_handover.py`,
`test_project_order_inquiry_import_instalments.py`,
`test_order_inquiry_form_raises_rows.py`. `test_project_order_inquiry_import_reader.py`
and `tests/scm/test_scm_import_tasks.py` stay; the task test's asserted result
keys move to the new set.

Frontend, `OrderInquiryUploadDialog.test.tsx` (extend the existing spec):

* AC-S2-1 `renders six tiles from the preview`.
* AC-S2-2 `omits an empty chip list`.
* AC-S2-3 `formats line_not_found entries with the reason in words`.
* AC-S2-4 `confirm disabled when nothing would be raised`.

## 5. Slices

| slice | scope | phase |
| --- | --- | --- |
| S1 | importer rewrite, preview, result, retired tests | Phase 2 (tester red -> coder green) |
| S2 | dialog preview panel + types | Phase 1 mock against the AC-S1-22 shape, then swap to real in Phase 2 |

Order: S2 mock first (frontend-first rule), then S1 red tests, then S1 green,
then S2 swap. One lane, one branch `feat/oi-sheet-migration`, one PR.

## 6. Out of scope, named

* The 12 sheet-owned sales orders (`source_system = scm_order_inquiry`) on
  prod. AutoCount's ingest owns the same numbers now; whether those rows are
  superseded or removed is a separate backfill question (backlog).
* Reconciling the 1,081 open `order_inquiry` claims older uploads left.
* Unplacing or moving rows the sheet no longer states. D2 is skip-only.
* A dedicated upload button on the Order Inquiries page. The reorder page's
  button is where the operator is today.
