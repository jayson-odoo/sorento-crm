# OI-ONE-DELIVERY-DATE owner card (3 Nov 2026)

Status: CARD POSTED, waiting on the owner (Q1 to Q5). Size L, LEAD pattern, full track
(data migration). No code until the card is answered.

Owner ask (3 Nov 19:15): "we only need one delivery date, which is the SO line delivery date ...
drop the delivery date in the order inquiry row and reference it by the SO line ... I don't want to
cause confusion at the stock debt, at email. We can show the changes in the order inquiry, but I
just want one delivery date." Example: OI-2609-0588 CB55CR rows read 01/09/2026 and 01/10/2026;
Stock Debt shows their SO397450 lines due 04/02/2027 and 18/02/2027; the "Request CS to reserve"
dialog shows the OI dates.

## What exists today (read, not assumed)

**The SO line date is already one value.** AutoCount's SO line `DeliveryDate` lands on core
`sales_order_lines.required_date` (`app/services/document_ingest_service.py:250`, written
`:1626`/`:1657`), and the project mirror line follows it on every push
(`_sync_mirror_line`, `:1461`: `mirror.delivery_date = core_line.required_date`). A manual SO edit
writes both (`app/services/scm/sales_order_service.py:1993`, `:1998`). Stock Debt reads only
`required_date` (`app/services/scm/stock_debt_service.py:1614`, `:1670`, drill `:609`).

**The OI row keeps its own copy, `projects.order_inquiry_rows.delivery_date`**
(`app/models/project_so.py:1017`), plus `previous_delivery_date` (`:1108`) for Was / Now. The copy
drifts from the SO line in two ways:

1. **Sheet migration writes the sheet's date, not the line's.**
   `app/services/project_order_inquiry_import_service.py:2827`:
   `delivery_date=row.delivery_date or match.core_line.required_date`, per an owner ruling of
   18 Sep 2026 ("we should have followed the sheet's date"; SO314593: sheet 1.9.2026, line
   01/03/2027). **This card reverses that ruling.** OI-2609-0588 (Sep, month-start dates) fits this
   shape; query 1 in `OI-ONE-DELIVERY-DATE-examples.sql` confirms it on dev data.
2. **An AutoCount date change does not touch the OI row.** Ingest only records a planning-change
   diff (`document_ingest_service.py:1258`, `:1295`); the row moves only when CS confirms that
   change (`app/services/project_order_inquiry_service.py:3281` `_stamp_date_move`, `:3005`
   `_settle_row_in_place`, or a new DELAY/ADVANCE row, `app/services/planning_change_service.py:3934`).
   Until then the OI says the old date and Stock Debt says the new one.

Nothing pushes an OI date to AutoCount. MCP and the chatbot read no OI date.

## Every place the OI row's own date is shown or used

| Surface | Where (file:line) | Today | After |
| --- | --- | --- | --- |
| OI Lines grid / worklist (value, server sort, default sort) | `order_inquiry_worklist_service.py:844`, `:874`, `:174`; project lines `project_order_inquiry_service.py:8387` | OI row date | SO line date |
| Worklist filters: delivery month, from / to, month sheets, matrix | `order_inquiry_worklist_service.py:1471-1475`, `:1688-1693`, `:3366-3374`, `:3562-3572` | OI row date | SO line date |
| Was / Now on the OI (host changes, previous columns) | `order_inquiry_worklist_service.py:935`, `:2341-2381` | `previous_delivery_date` vs row date | see Rule 3 |
| Request CS to reserve: dialog rows + request email + reserved notice | `order_inquiry_reserve_service.py:331-332`, `:464-465`, `:560-568` | OI row date | SO line date |
| OI handover email body, send preview, Excel attachment | one builder: `handover_item` `project_order_inquiry_service.py:4790`; Excel `order_inquiry_worklist_service.py:4045-4080`; templates `oihr_0001..0005` | OI row date, `was` for DELAY/ADVANCE | SO line date, `was` unchanged (tally by construction, same lines feed all three) |
| Resend / "Send to purchasing" preview | `oi_handover_resend.py:108`, `:132`, `:243` | OI row date | SO line date |
| Undo email | `project_supply_undo_service.py:984-1000` | OI row date | SO line date |
| Confirm preview (inquiry rows it lists) | `project_supply_service.py:635`, `:12348` | OI row date | SO line date |
| Stock Debt snapshot, frozen OI | `scm/stock_debt_snapshot_service.py:202` | OI row date (live view already uses the SO line) | SO line date |
| Link suggestions: "arrives in time" window, candidate order | `order_inquiry_worklist_service.py:1969-2047`, `project_order_inquiry_service.py:12029`, `:12503`, `:13377`, `:13991` | OI row date | SO line date |
| ETA fallback, waiting-row ranking | `planning_change_service.py:1632`, `:1686-1688`, `:4151` | OI row date | SO line date |
| Plan / reorder demand legs (horizon, need dates, month buckets) | `scm/demand.py:766-770`, `:850-854`, `:1058-1083`; `scm/demand_breakdown_service.py:644-663`, `:751-772`; `scm/summary_order_service.py:793`, `:865`; `api/v1/scm/reorder_runs.py:544`, `:579`; `scm/spo_conversion_service.py:1209` | OI row date (book leg already uses `required_date`) | SO line date |
| Sheet upload "Dates corrected" tile | FE `scm/reorder/components/OrderInquiryUploadDialog.tsx:167` (`rows_delivery_date_updated`) | upload rewrites OI dates from the sheet | upload no longer moves dates; the tile goes |

**Frontend (26 reads, all display / sort / filter; no screen edits the date).** Every one takes the
value from a backend field, so the backend change carries them; paths under
`sorento_crm_frontend/app/(protected)/`:

- OI worklist + OI detail Lines tab + History dialog + Request-reserve dialog + Stock Debt snapshot
  drill reserve rows: one endpoint, `GET /api/v1/project-sales/order-inquiries`
  (`project-sales/order-inquiries/components/orderInquiryWorklistColumns.tsx:819-828`, `:1180`;
  `[id]/components/orderInquiryHeaderLinesColumns.tsx:737`; `_shared/components/RequestReserveDialog.tsx:203-233`;
  `[id]/components/OrderInquiryLineHistoryDialog.tsx:101-117`). Month tabs, schedule matrix and its
  drilldown, unlink-all and exports use the same `delivery_month` / `delivery_from` / `delivery_to`
  filters (`OrderInquiriesClient.tsx:413-440`, `OrderInquiryScheduleMatrix.tsx`).
- Was / Now dialog: `OrderInquiryQtyAnnotationDialog.tsx:118-132` -> `BoardChangeWasNowTable`
  (was = `previous_delivery_date`). Bundled-host tooltip: `_shared/lib/orderInquiryAck.ts:166-184`.
- Link lightbox "needed <date>" and "Due after <horizon>": `orderInquiryWorklistColumns.tsx:297-348`,
  `_shared/lib/linkHorizon.ts:182-190`.
- Email send / resend preview tick list: `_shared/components/HandoverResendDialog.tsx:121`.
- Per-project OI list: `project-sales/[projectId]/order-inquiries/components/OrderInquiryClient.tsx:219-232`
  (`GET .../projects/{pid}/order-inquiry-rows`).
- SCM reorder demand popover and SPO "SO covered" picker show the OI date as `required_date`
  (`scm/reorder/components/PlanDemandPopover.tsx:249`, `scm/components/PlanRowDialog.tsx:1876`).
- Found on the way, outside this lane: the OI detail Lines tab sorts client-side
  (`OrderInquiryLinesTab.tsx:180`, `getSortedRowModel`), against the "all grid columns sort
  server-side" rule. Proposed as a separate small lane, not folded in here.

## Rules (proposed)

1. **The date.** An OI row's delivery date IS its SO line's date: core `required_date` through
   `order_inquiry_rows.so_line_id -> projects.sales_order_lines.core_sales_order_line_id`, and the
   mirror line's `delivery_date` when the mirror is not reconciled to a core line yet (same value
   otherwise, `document_ingest_service.py:1461`). One SQL expression and one Python helper, used by
   every reader in the table above; nothing else computes it.
2. **The column stays, renamed in meaning only: "the date purchasing was last told".** It is what
   the DELAY / ADVANCE email logic diffs against (`_handover_settle_diff`,
   `project_order_inquiry_service.py:486-516`) and what undo restores
   (`project_supply_undo_reconstruct_service.py:454-467`). No screen, email, attachment, export or
   plan reads it as "the delivery date" any more. Every writer that today writes a non-SO date
   (the sheet import, `:2827`) writes the SO line date instead. Dropping the column is a later lane,
   only if nothing reads it (it will still be read by Rule 3).
3. **Changes show on the OI as Was / Now.** When the SO line date differs from the date purchasing
   was last told, the OI row reads `Now <SO line date>` with `Was <told date>` beside it (Q1). After
   CS confirms the planning change the OI email says DELAY / ADVANCE exactly as today, and the Was
   stays from `previous_delivery_date` as today.
4. **One-off backfill (data migration, no schema change).** Every live row (state not `cancelled`)
   with an SO line whose stored date differs: `previous_delivery_date := delivery_date`,
   `delivery_date := SO line date`, so the OI shows "Was 01/09/2026, Now 04/02/2027" for the sheet
   rows (Q2). Counted and logged per OI; reversible from the migration's own log table.
5. **Rows with no SO line** keep their own date (Q4); the reserve dialog, email and grid show it
   unchanged.
6. **Emails tally.** Email body, preview and Excel all come from `handover_item` lines, so changing
   the one `delivery_date` read there changes all three. Reserve emails keep the 31 Oct rules (full
   table, one email per raised_by CS, button opens exactly that email's OIs, no TOTAL QTY,
   "Rejected"); only the date column's source changes.

## Edge cases

- **Pending AutoCount change, not yet confirmed by CS:** Rule 3, Q1.
- **Sheet-migrated rows purchasing has been working to:** Rule 4, Q2. This is a real behaviour change
  for purchasing (SO314593's note at `:2817-2826` is exactly this case).
- **Split SO line (OI-LINE-SPLIT tranches, `projects.so_line_splits`):** each tranche has its own
  date and an optional `sits_on_line_id` (the AutoCount line staff picked). Q3.
- **Legacy duplicate rows on the wrong SO line:** reading the linked line's date shows that line's
  date, which may be wrong for the row. Q5.
- **SO line deleted:** `so_line_id` is SET NULL (`project_so.py:1011-1014`), so the row falls under
  Rule 5 with its last stored date.
- **Several OI rows on one SO line with different dates** (query 5): all read the one line date; the
  rows still differ by quantity and links. If Q3/Q5 answers leave none of these, the email's split
  "was" line reads the same as today.

## Real examples (dev data)

This sandbox has no copy of dev data. `OI-ONE-DELIVERY-DATE-examples.sql` (read-only) pulls:
(1) OI-2609-0588 row by row, OI date vs SO line date; (2) how many live rows differ / agree / have
no SO line; (3) mirror vs core drift (expected 0); (4) the five largest gaps; (5) SO lines carrying
several live OI rows with different dates, split or not; (6) rows with no SO line by verb. Crew:
please run it on the dev copy and paste the output under this heading; the 3 to 5 examples for the
hand test are taken from (1), (4) and (5).

## Questions (recommendation first)

- **Q1. AutoCount moved the SO line, CS has not confirmed the planning change yet.** (a) The OI,
  reserve dialog and emails show the new SO line date at once, with "Was <old>" on the OI row until
  CS confirms; (b) keep the old date until CS confirms. **Recommend (a)**: (b) is exactly the
  "two dates" confusion between OI and Stock Debt.
- **Q2. Sheet-migrated rows that carry the sheet's date (reverses the 18 Sep ruling).** (a) Backfill
  to the SO line date, Was = sheet date shown on the OI, no email; (b) same, plus one DELAY / ADVANCE
  email per OI to purchasing. **Recommend (a)**: the SO did not change, so purchasing is not being
  told news; a burst of emails for a data fix would bury real changes. Crew sends the owner the
  count from query 2 before the migration runs.
- **Q3. Split tranches.** (a) A tranche that sits on an SO line shows that line's date; a tranche with
  no sits-on line yet (AutoCount has not added the line) shows its planned date marked "planned"
  until AutoCount does; (b) every tranche shows its parent SO line's date. **Recommend (a)**: (b)
  prints one date for parts that will arrive months apart, which is the opposite of the split's
  purpose.
- **Q4. Rows with no SO line** (line deleted, stock / manual rows). (a) Keep their own date;
  (b) show blank. **Recommend (a)**: it is the only date the row has.
- **Q5. Legacy duplicate rows sitting on the wrong SO line.** (a) Show the linked line's date and
  list such rows (query 5) for CS to repoint with the existing repoint action; (b) auto-repoint each
  to the same-item line whose date matches. **Recommend (a)**: an automatic repoint moves links and
  netting nobody asked for; (b) is its own lane if the list is long.

## Build outline (after answers)

1. Red tests from the UAC: helper + SQL expression; each surface in the table returns the SO line
   date (worklist value, sort, month filter; reserve dialog + email; handover email = preview =
   Excel; stock debt snapshot; plan legs); Was / Now when told date differs; backfill migration
   up / down on a seeded chain; no-SO-line row keeps its date.
2. Helper `oi_delivery_date` (Python) + `OI_DELIVERY_DATE_SQL` (one expression) in
   `project_order_inquiry_service.py`; replace each read in the table.
3. Sheet import writes the SO line date.
4. Data migration (no DDL), chained onto main's head at build time.
5. Frontend: the "Delivery date" column header stays the same, the Was shows beside it
   (`DeliveryDateCell`), and the upload's "Dates corrected" tile goes. No other screen changes,
   because every screen reads the backend field.
