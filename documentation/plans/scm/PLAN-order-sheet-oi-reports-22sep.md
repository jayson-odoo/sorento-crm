# PLAN: order sheet fixes, OI worksheet for a plan run, async OI export

Status: APPROVED 22 Sep 2026 (owner "ok" after six grill rounds). Lane A IN PROGRESS - worktree `../sorento_crm-order-sheet-cells`, branch `fix/order-sheet-cells`, tests on `sorento_osc_ci`. B, C queued; D after #1122.
UAC: `order-sheet-oi-reports-22sep-acceptance-criteria.md`.

## What the owner asked (22 Sep 2026, order sheet screenshot + OI report sample)

1. Order sheet: BRW incoming qty and Last in qty must not print the SPO number.
2. Order sheet: Project / customer reads like the Project column on Order Inquiries.
3. Explain the numbers (Suggestion column, and why SRTWB248 buys 67 with 56 on hand).
4. New report: the OI lines behind a reorder plan, in the ORDER INQUIRY tabular format
   purchasing already uses (SO DATE / S/O NO / ITEM CODE / QTY / TOTAL QTY / DELIVERY DATE /
   PROJECT/CUSTOMER / SUPPLIER / PO NO), so they can tick every line against a PO in
   AutoCount.
5. Order sheet: one more column right of Supplier - last purchase cost. Supplier = last
   purchase supplier.
6. OI detail Export Excel: async, lands in My Downloads, tied to the OI so its download
   history is reachable from the OI.

## Measured (0921 prod copy, run 9e2254f6 of 21 Sep)

- Supplier on the sheet is ALREADY the last-purchase supplier: `_last_po_supplier_map`
  reads the newest non-cancelled PO line per product (issue_date desc). Nothing to change.
- The sheet's three project cells (Project qty, Delivery, Project / customer) come from
  `_project_inquiry_map`, which INNER JOINs `projects.so_supply_decisions` with
  `state = 'active'`. On the copy 12,261 of 12,763 live OI Buy rows have NO supply decision
  (form-raised / uploaded rows; only 501 went through the board). Those rows never reach
  the three cells. The engine (`demand.py` project select) reads BOTH legs - the confirmed
  leg with a decision AND the form leg with `supply_decision_id IS NULL` - so it buys for
  them. That is the whole SRTWB248 story: SO418869 (WATER CARE / EUGENIA), 67 units at
  BRW-IR, delivery 01/10/2026, OI row verb ORDER state raised, no decision. Engine: Buy 67.
  Sheet: Project qty 0, Delivery blank, Project / customer blank.
- Project / customer label: `_project_inquiry_map` prints `customer_name / projects.title`.
  Adopted AutoCount orders have `project_id` NULL by design, so the cell shows only the
  customer ("APEX CONNECTION SDN BHD (PROJECT)"). The OI worklist prints
  `project_customer_label(customer, coalesce(Project.title, SalesOrder.project_label))`
  (PR #1084), which is why it reads "APEX CONNECTION / DNC / TITAN RITZ / D NOVA".
- Suggestion text (`_suggestion_text`, channel runs): `Stock <BRW on hand> + PO <open PO
  qty> + Buy <Suggested qty>`. Stock and PO are the supply figures the engine counted, not
  amounts applied to the need; the three parts do not add up to Project qty and were never
  meant to. Suggested qty is the engine's buy inside the plan window, net of stock and PO.
- Async downloads already exist for the order sheet + low stock report
  (`user_downloads`, `source_entity_type = reorder_run`), for complaints
  (`generate_complaint_pdf`, `EntityDownloadsButton` "Download history" in the gear).
  The OI detail's Export Excel is the only sync one: `GET /order-inquiries/export?
  inquiry_id=` streams bytes and `saveBlobAs`.
- The ORDER INQUIRY tabular format the owner pasted IS `OrderInquiryWorklistService.
  export_xlsx` (EXPORT_HEADINGS, one sheet per delivery month, SUPPLIER then ITEM CODE).
  The new report is that writer over a different row set, not a new writer.
- Engine's last-purchase cost per product already exists: `reorder_engine.
  last_purchase_costs` (newest PO line with `unit_cost IS NOT NULL`, per supplier).

## Lane A - order sheet cells (small fix track candidate: one module, no migration)

Seam: `app/services/scm/summary_order_service.py` (+ `low_stock_report_service.py` shares
the cell builders, so it inherits A1/A2/A3 for free).

- A1 `_docs_text` for BRW incoming qty and `_last_in_text` drop the SPO number:
  `<container> - <qty>` per line, bare qty when the line names no container. BRW PO qty
  keeps its PO numbers (not asked). **R1 (owner, 22 Sep): container + qty.**
- A2 `_project_inquiry_map` label = `project_customer_label(customer_name,
  coalesce(pj.title, so.project_label))` imported from `project_order_inquiry_service`, so
  the sheet, the OI worklist and the OI detail spell one row the same way.
- A3 `_project_inquiry_map` reads the OI book directly, **scoped to the run** - owner
  rulings 22 Sep: "read from OI, don't care about supply decision", then "the project qty
  should be lesser", "I need the quantity here to make perfect sense". The
  `so_supply_decisions` join goes. The predicate is the ENGINE's own OI row predicate
  (captain ruling 23 Sep after review: the plan's first cut, "state <> cancelled, ack not
  rejected", admitted 2,006 placed + 5,713 actioned + 474 awaiting-ack + 12 redirected rows
  on the 0921 copy that the engine never buys for, so Project qty would have run ABOVE Buy
  instead of tallying): verb in (ORDER, ORDER_BACK), state in (raised, partly_linked),
  ack_state in (acknowledged, changed), not redirected to pool, owed qty (qty minus linked)
  > 0, printed qty = owed; product = the CORE line's product (`sol.product_id`, as the
  engine's confirmed leg reads it); SO in `run.so_numbers` when set, product in
  `run.product_ids` when set, delivery date inside `[plan_horizon_start,
  plan_horizon_date]` (undated included). Lane C prints the same rows.
  Result: Project qty = the rows the engine bought for, so on a Project run with buy-in-
  full Project qty == Buy, and Delivery / Project-customer list exactly those rows. One
  helper (`run_scope_oi_rows(db, run)` in `demand.py`) feeds both `write_rows` and Lane
  C. Freeze-time change; rerun to see it.
- A3b Suggestion text becomes one part per line - owner: "the + + should be separated
  into lines so it is easier to see": `Stock: 438` / `PO: 11` / `Buy: 67` on the XLSX
  (wrapped cell) AND the PDF (column 6 joins `_PDF_LIST_COLUMNS`). `Nothing` stays one
  word. SHEET ONLY: the plan grid's Decision pill is a one-line control and derives its
  own label on the FE (`lib/planEdits.ts`); it is untouched (captain, 23 Sep - the owner's
  ask was made on the sheet).
- A4 New column "Last cost" immediately right of Supplier, order sheet PDF + XLSX. Value =
  the newest non-cancelled PO line's `unit_cost` + currency for the product (same
  DISTINCT ON as the supplier lookup, extended to select cost/currency), joined at EXPORT
  time like Description/Category on the low stock report - no new frozen column, no
  migration. Printed `12.50 CNY`; blank when the line has no cost. **R2 (owner): one text
  cell; currency NEVER hard-coded** - `COALESCE(pol.currency, po.currency)`, the header's
  currency when the line carries none (AutoCount lines carry no currency; PR #1124 fixes
  the CNY fill and backfills the 66,720 mislabelled lines, so this column must not
  re-introduce the assumption). Low stock report does not get the column (not asked).
  Widths/PDF column maps shift by one (`_XLSX_COLUMN_WIDTHS`, `_PDF_LIST_COLUMNS`,
  `_PDF_NUM_COLUMNS`) - the tests pin them.

Tests: pytest on `_docs_text`/`_last_in_text` shapes, the label rule, the A3 predicate
(seed one form-leg row with no decision and assert it lands in Project qty), the new
column position on both formats.

## Lane B - OI detail Export Excel goes async and is tied to the OI

- B1 `POST /order-inquiries/{inquiry_id}/export` creates a `user_downloads` row
  (`kind = order_inquiry_xlsx`, `source_entity_type = order_inquiry`, `source_entity_id =
  inquiry id`, filename `<OI number>.xlsx`), enqueues `generate_order_inquiry_xlsx`
  (`export_tasks`, queue `imports`) which calls the existing `export_xlsx(inquiry_id=...)`
  and `mark_ready` with the bytes; enqueue failure marks the row failed (complaint
  pattern, verbatim). In-flight guard via `has_in_flight` like the order sheet (AC-21 of
  that plan): a second click while one is queued starts nothing.
- B1b **R4 (owner): the OI LIST page's Export Excel goes async too**, untied to any
  record: `POST /order-inquiries/export` with the same filter body the GET takes, kind
  `order_inquiry_worklist_xlsx`, no source entity, filename `order-inquiries-<ddmmyyyy>.xlsx`;
  same task with `inquiry_id` absent. The GET stays for one release (MCP/other callers),
  then retires.
- B2 OI detail: Export Excel toasts "Queued - see My Downloads"; the gear gets "Download
  history" opening `EntityDownloadsButton` for (`order_inquiry`, id), exactly the complaint
  detail's placement. The list page's Export Excel button toasts the same way (B1b).
- Worker restart needed (new task in `app/tasks/*`).

## Lane C - "Order inquiry worksheet" for a plan run

Owner's process (22 Sep): **this sheet comes FIRST.** Purchasing downloads the OI rows in
the run's scope, then the engine decides stock / buy / SPO per row, then the decision is
executed. So the row set is the run's SCOPE, not the engine's verdict. Reconciliation
against AutoCount POs is done offline for now.

- C1 Export menu on the plan view gains "OI worksheet Excel" beside Order sheet / Low stock;
  same `useExport*` hook shape, one pending flag for all four items; `source_entity_type
  = reorder_run`, `kind = oi_worksheet_xlsx`, filename `oi-worksheet-<ddmmyyyy>.xlsx`.
- C2 Row set = every live OI Buy row (verb ORDER/ORDER_BACK, state <> cancelled, ack not
  rejected, qty > 0) that satisfies the run's own Start Plan scope, read off the
  `reorder_run` row: `so_numbers` (when set), `product_ids` (when set), `demand_class`
  (Project = OI rows only; Dealer/All = the same OI predicate, there is no OI for retail),
  and delivery date within `[plan_horizon_start, plan_horizon_date]` (undated rows
  included, as the engine does). A raised-date filter, once PR #1123 stores one on the run,
  applies the same way - **owner: "raised at, sales order delivery, orders, products in
  Start Planning, so all should tally"**. A run's far-month rows are OUT. Products with no
  sheet row still appear if their OI row is in scope: the sheet is the input, not the
  output.
- C3 Writer = `OrderInquiryWorklistService.export_xlsx` with a `row_ids` filter fed by
  `run_scope_oi_rows` (delivery_from/to already exist; `so_numbers` and
  `product_ids` list filters are new). **Owner: no ACKNOWLEDGED column** - the worksheet
  writer takes a `columns` argument that stops at LOCATION; the list-page export keeps it.
- C4 Task `generate_oi_worksheet(download_id, run_id, user_id)` in `export_tasks`.
- C2 and A3 share `run_scope_oi_rows`; C branches from A's lane or waits for its merge.

Tests: pytest for C2's row set on a seeded run (one row in window, one outside, one from a
different SO, one for a product not in `product_ids`), the new list filters, the column
cut, the task's mark_ready. Vitest for the menu item + pending flag.

## Answers the owner asked for (kept here so the sheet's readers can find them)

The screenshot run was Demand: Project with selected sales orders, window 01/09 to 16/11.
In that mode Buy = the selected SOs' OI Buy rows due inside the window, bought in full
(owner ruling R1a, 22 Sep: stock and open PO are not netted against project need). Stock
and PO in the Suggestion text are only what is on hand at BRW and on open PO. Project qty
today counts OI rows that carry a board decision, every SO and every month, so it is 0 on
seven of the twelve rows and unrelated to Buy on the rest (A3 fixes it). Traced on the 21
Sep copy:

| Item | Buy | Source OI rows |
| --- | --- | --- |
| B2155-NL-BLUE | 961 | selected SOs' rows in window (OIB 700, Super Ceramic 156, Bathe Code 85, Mah Sing 15, ...) |
| CB2805A-DIY | 246 | SO402757 OIB / Myra Cove 246, 01/11 |
| CB2829-DIY | 128 | SO419517 OTM / Tat Lian 58 + SO418869 Water Care / Eugenia 70 |
| CB771 | 205 | SO418869 Water Care / Eugenia 205, 01/10, BRW-IR |
| CBT001-NL | 54 | SO420955 Kenwealth / Public Bank Bangi 54, 25/09 |
| MSP124 | 43 | SO420374 Bathe Code / Ban Hong 43, 02/11 |
| SRTWB1515 | 164 | SO402757 OIB / Myra Cove 164, 01/11 |
| SRTWB248 | 67 | SO418869 Water Care / Eugenia 67, 01/10, BRW-IR |
| SRTWB7237 | 82 | SO402757 OIB / Myra Cove 82, 01/11 |
| SRTWCX7405-RL-S-PJ | 164 | SO402757 OIB / Myra Cove 164, 01/11 |
| SRTWHBWP | 82 | SO402757 OIB / Myra Cove 82, 01/11 (9,922 on hand, bought in full per R1a) |
| SRTWT2207 | 67 | SO418869 Water Care / Eugenia 67, 01/10, BRW-IR |

Flagged to the owner: R1a means SRTWHBWP buys 82 against 9,922 on hand. Changing that is a
ruling on PR #1122, not this plan.

## Lane D - plan All with picked project SOs, retail via Dealer o/s

Owner, 22 Sep: "when we plan, I can only choose either project or retail, actually I want
to plan all, but for project I want to select specific SO which is linked to related OI,
the retail order contributes to dealer O/S qty." Then: "no, this should be 1 plan" - so it
is in scope here, on top of PR #1122 (branch from it, or from main once it merges).

Measured (main + #1122 worktree): `RunPlanningModal` sends `demand_class` only when the
buyer picks Project or Dealer and `so_numbers` only under Project; the Orders picker is
hidden under All. Backend honours `so_numbers` only when `demand_class == "project"`
(`_planning_rows` via `horizon_committed_select_sql(so_scoped=...)`,
`_apply_project_supply_reduction` line 1335). An All run therefore plans EVERY project
order in the window plus the retail leg. #1122 makes a Project run leg-1-only and
project-need-only.

- D1 Modal: the Orders picker shows under Demand = All as well as Project (same candidate
  query, same "everything in range ticked by default", same touched-by-hand rule). It is
  the existing `SearchableMultiSelect` already in the modal - owner: "use our existing
  multi select component, not a bloated picker", then "just one line, with extra as +x" -
  so the trigger uses the component's existing `renderTriggerLabel` to print ONE line:
  the first two SO numbers then `+x` (`SO418869, SO419517 +12`), no chip wall; the menu
  rows drop the two-line `renderOption` (description + "awaiting ack") for one line,
  `SO number - customer`, with the awaiting count as a small suffix only when non-zero.
  Wire: `so_numbers` may accompany an All run (`demand_class` absent). Dealer keeps no
  picker.
- D1b The From / To range is labelled "Project delivery range" and, on an All run, windows
  the PROJECT legs only - owner: "this order range only is for project". The retail book
  leg on an All run plans every open line, as an unhorizoned run does today. A Dealer run
  and a Project run keep today's reading of the range.
- D2 Backend: `so_numbers` scopes the PROJECT legs of an All run - `horizon_committed_
  select_sql(demand_class=None, so_scoped=True)` narrows only the two OI legs; the SO-book
  retail leg and leg-2 admission (below level, moved in 180 d) are untouched, so the retail
  side still sizes from the level trigger with dealer outstanding inside `committed`.
  `_apply_project_supply_reduction` and `run_scope_oi_rows` (A3/C2) read `so_numbers`
  whenever set, not only under Project. Stamped on the run as today.
- D3 Sizing unchanged: `_emit_pool` / `_emit_cell` / `_emit_product` already add the
  project need on top of the retail sizing on an All run (`recommended =
  retail_recommended + pool_project_need`, buy-in-full R1a). Nothing new to size; the
  change is which project rows reach `committed`.
- D4 Sheet: Project qty / Delivery / Project-customer on an All run = the picked SOs' OI
  rows in window (A3, which keys off `so_numbers` regardless of class); Dealer o/s is the
  retail leg's own figure as today. The OI worksheet (C) prints the same picked rows.
- D5 A run with Demand = All and NO picked orders keeps today's behaviour (every project
  order in range) - the empty-list-means-nothing rule applies only when the picker was
  shown and everything unticked, same as Project.

Tests: pytest on `_planning_rows` for an All run with `so_numbers` (project row on an
un-picked SO absent from `committed`; retail-only product still admitted by leg 2 and
sized by level; picked SO's project need bought in full on top). Vitest: picker visible
under All, payload carries `so_numbers` with `demand_class` absent.

## Sequencing

A first (it changes the numbers purchasing reads), then B and C in parallel (independent
seams; B and C both touch `export_tasks.py` and `order_inquiry_worklist_service.py`, so
whichever merges second rebases). D after #1122 merges (it edits the same
`_planning_rows` branches); A3's helper is written so D needs no change to it.

## Rejected

- Freezing last cost onto `order_summary_row` (two columns + migration): the export-time
  join is the same shape the low stock report already uses for master data, and a cost that
  moved since the run is the cost purchasing pays today.
- A second XLSX writer for the OI worksheet: the sample the owner pasted is the worklist
  export's own layout, pixel for pixel.
- Making Project qty read the SO book instead: it would then disagree with the OI-only
  Project plan (PR #1122) the owner just ruled on.
- Scoping the OI worksheet to the engine's Buy verdict: the owner uses the sheet BEFORE the
  engine decides, so it must list the scope, not the answer.
