# UAC: SCM fulfilment feedback part 4

**Status:** GRILLED round 2 (2026-08-27), awaiting GO. Plan: `PLAN-scm-fulfilment-feedback-p4.md`.
Every AC is checked in a real browser on the dev server (agent-browser, sidebar navigation from `/`) and, where a backend rule is named, by a pytest on Postgres.

## A. Loading plan list and record (S1)

- **AC-A1** `/scm/loading-plan` (sidebar: Supply Chain > Loading Plan) renders a DataGrid with columns Started, Supplier, SO cut-off, Document, To request, Sent, Opened, Status; `listingKey scm.dashboard.view::loading-plans`; column order/visibility persist; usable at 375px and 1280px.
- **AC-A2** Default sort Started desc; search box filters by supplier name; the Filters popover has Status with default chip "Active" (planning + sent); choosing Cancelled shows cancelled plans.
- **AC-A3** The toolbar's ONLY primary action is "Upload". No other Upload button exists on the list or the detail page.
- **AC-A4** "Upload" opens "Plan a container": Supplier (searchable, required), "Sales order cut-off" (date, clearable, hint "Empty = every open order counts."), Document radio (Stock list / Proforma invoice / No file). The label "Plan until" appears nowhere in the app.
- **AC-A5** Choosing Stock list or Proforma invoice reveals the drag-and-drop dropzone INSIDE the same dialog; Test shows the verdict card; Confirm creates the plan, applies the file, and lands on `/scm/loading-plan/{id}` with the figures of that file. No second dialog opens.
- **AC-A6** "No file" + Start plan creates the plan and lands on the detail with the PI stand-in (Q2 of part 3) or the empty universe, as today.
- **AC-A7** Whole-row click opens `/scm/loading-plan/{id}`; the detail has prev/next record navigation across the list.
- **AC-A8** Row action Cancel asks "Cancel this plan?" (ConfirmActionDialog); on confirm the status reads Cancelled, the row leaves the Active filter, the detail is read-only (Save and Send disabled with the reason), and the supplier link returns the "no longer available" page (Q4).
- **AC-A9** Row action Delete asks (ConfirmDeleteDialog) and hard-deletes an unsent plan with its edits; a sent plan's Delete is disabled with title "Sent plans are cancelled, not deleted".
- **AC-A10** Backend: `GET /api/v1/scm/loading-plans?page&limit&sort&dir&query&status` returns `{data,total}` with the list fields; `POST /loading-plans` creates `{supplier_id, plan_horizon_date, document_kind, source_attachment_id}` with status `planning`; `POST /loading-plans/{id}/cancel` stamps `cancelled_at/by`; `DELETE` 204 on unsent, 409 `code="plan_sent"` otherwise. Migration 441 (renumbered from 440, which S6 took) adds the columns plus the `to_request_qty` / `to_request_cbm` the grid prints, relaxes `container_cbm`/`capacity_cbm`, single alembic head.
- **AC-A11** `POST /container-requests/build` takes `plan_id`; the response carries `plan {id, supplier, plan_horizon_date, status, document_kind, started_at}` and every line carries `engine_qty` and `suggested_qty` (edit applied). The old `{supplier_id, plan_horizon_date}` body returns 422.
- **AC-A12** Detail toolbar: title = supplier name; subtitle "Started dd/mm/yyyy HH:mm · SO cut-off dd/mm/yyyy · <document>"; status badge; right cluster in order [gear] [Save (N)] [Send to supplier] [Back to loading plans]. The old header card (Supplier / Plan until / Upload) is gone; the "What to ask" card shows the heading only.
- **AC-A13** The gear (`aria-label="Plan actions"`) holds: View uploaded list (only with an attachment), Refresh matching, Refresh suggestion, Copy link (disabled "No link sent yet"), Download XLSX, Download PDF, Change cut-off, Cancel plan, Delete plan.
- **AC-A14** Typing a suggested qty enables Save (N) where N = rows differing from `engine_qty`; Save writes `PUT /loading-plans/{id}/edits` (whole map, one transaction) and a reload shows the typed values; Save (0) is disabled.
- **AC-A15** Send to supplier with unsaved edits saves first; the sent xlsx carries the typed quantities. Navigating away with unsaved edits prompts.
- **AC-A16** Refresh suggestion with edits present asks "Drop your N typed quantities?" and clears `line_edits` on confirm.
- **AC-A17** Uploading a newer stock list for the same supplier from a NEW plan changes an older open plan's On hand / Packed figures on next open (documented behaviour, R2), and the older plan's Document subtitle still names ITS file.

## B. Lightboxes (S2)

- **AC-B1** On the loading plan grid, clicking the Project, Retail, On hand, SPO, Incoming PL, PO, Project peak or Retail peak figure opens a Dialog shaped like reorder planning's lightboxes (tabs Open · History where the table lists them, document rows, › expands to lines) (`role="dialog"`, `sm:max-w-[95vw]`, `max-h 85vh`), never a Popover; Escape and the X close it; usable at 375px.
- **AC-B2** Project / Retail dialogs: tab "Open ... (n)" lists Sales order, Customer, Project, Agent, Price, Qty, Required with a total row equal to the cell; tab "12-month history" shows both series with the peak month named.
- **AC-B3** On hand dialog = reorder planning's On hand lightbox: Location, On hand, Reserved, Free, SO qty, SPO qty, Available, PO qty, › documents, "Stock as of"; site pools only; total = cell. **Amended 28 Aug:** the cell counts ACTIVE locations only, the cut the lightbox and `_pool_warehouses` already made - 17,356 units in closed pool locations were being netted off asks (pytest seeds stock in a closed warehouse; browser: SRTWB241 286/286).
- **AC-B4** SPO dialog (tabs Open to pools · History; SPO, Packing list, To, Qty, Received, ETA, Status) reads the SPO documents where they are FILED and its open total equals the cell, which reads the same rows. **Amended 28 Aug on measurement (see the note under R8a in the plan): that is `spo_allocations`, not `purchase_order_lines` - migration 420 moved every SPO document off the PO table, which holds 0 units bound for a site pool against the cell's 3,051, so `_stock_context.incoming_spo` is unchanged and the guard AC-H1 is not re-baselined. Reverts to R8a as written the day SPO uploads land on `purchase_orders`.** Incoming PL dialog (Packing list, Container, Supplier, Qty, ETA, Status) reads unreceived `inbound_shipment_lines` and sums to the cell; PO dialog (tabs Open · History; PO, Supplier, Qty, Still to come, Unit price, Issued, ETA, Status) reads `purchase_order_lines` and its open "still to come" sums to the cell.
- **AC-B5** `GET /api/v1/scm/container-requests/drill?supplier_id&product_id&kind` returns `{kind, rows, total}` and `total` equals the corresponding `_stock_context` figure for that product (pytest asserts equality for each kind on a seeded chain, incl. a set row drilling on its driver member). **Amended 28 Aug:** the `spo` kind reads `scm.on_order_v`'s WHERE clause for clause, LEFT JOIN included, so an allocation with no shipment yet is in the dialog as well as in the cell (it reads "Not shipped"); 140 products and 19,843 of 20,532 units on order were otherwise missing from the dialog (pytest seeds an allocation with `inbound_shipment_id = NULL`; browser: SRTWB241 117/117).
- **AC-B6** Project peak / Retail peak open the Project / Retail dialog on its history tab with the clicked series focused; figures equal the cells.
- **AC-B7** The shared `PlanRowDialog` lives in `app/(protected)/scm/components/`; no DRILLED FIGURE on the loading plan is a popover any more (`SoLinesDrillPopover` is deleted, `ContainerRequestHistoryPeakCell`'s popover is gone, the schedule matrix's cell opens a dialog), and no `PopoverPortal` remains in `scm/loading-plan/components/` except `RankFactorsPopover`, which R7 keeps as a popover and which therefore keeps the pinned-column workaround that earned it.

## C. Send to supplier (S3)

- **AC-C1** "Send to supplier" opens "Send this request" with a channel radio Email / Chat; the bare confirm AlertDialog is gone.
- **AC-C2** Email: To chips prefilled with the supplier's email; the user can add addresses (invalid ones refused inline) and remove any; Send is disabled with zero recipients; the email goes to every chip (one `email_outbox` row per address, so one bounce cannot stop the rest); the notice row stores `recipients` (JSON list) and the Requests sent card lists them. A send that reaches the backend with zero addresses is a 422 `no_recipients` and writes nothing.
- **AC-C3** Chat = WeChat: a searchable picker over Respond.io contacts on the WeChat channel, prefilled with the contact whose phone equals the supplier's phone; with no match the picker is empty and the hint reads "No WeChat contact for this supplier yet"; Send is disabled until a contact is picked. With no WeChat channel connected in the workspace the Chat option is disabled with that reason.
- **AC-C4** A chat send goes through the composer's outbound path (`respond_chat_template_service.send_chat_message_for`): within the 24h window a text with the link, outside it the approved template for the `supplier_request_chat` use case; an outbox row (`integration_log`, `respond_io`, outbound) is written in every case; the notice reads sent, or failed with `last_error` when Respond.io refused the send. **Amended 28 Aug:** the xlsx is NOT attached as chat media - the link carries both files, and no WeChat channel exists to establish what it accepts (trigger under R10).
- **AC-C5** With no approved template and an out-of-window contact, the send is refused (422 `template_missing`) and nothing else changes: no notice row, and the supplier's existing live link is NOT retired. Same shape for `wechat_channel_missing` and `chat_contact_not_found`.
- **AC-C6** One send writes ONE notice row for the chosen channel only; no `skipped` chat row appears any more (pytest on `request_and_notify`).
- **AC-C7** The public page and its document downloads stamp `opened_at` (first), `last_opened_at`, `open_count` on the notice(s) of that token; the page still renders when the stamp fails (best-effort).
- **AC-C8** The list column Opened and the Requests sent card show "Opened n times, last dd/mm HH:mm" / "Not opened yet"; the plan status is `sent`, never `opened`. Both read `supplier_notice_service.latest_notice_for_plans`, so a resent plan never reports the opens of a retired link.
- **AC-C9** Migration **442** (renumbered from 441: S1 and S6 hold 440/441 in this lane) adds `recipients` JSONB, `opened_at`, `last_opened_at`, `open_count` (default 0) to `supplier_notices`, and backfills `recipients` from the existing `recipient`; single alembic head.

## D. Supplier document fidelity (S4)

- **AC-D1** With a retained stock list, the sent and downloaded xlsx opens in Excel as the supplier's own workbook: title row, header row, every merged range (序号 / 体积 / 总体积 per family), yellow fills, fonts (宋体 / Calibri 14), column widths, row heights and the 合计 row are byte-for-byte those of the uploaded file, plus column K `需装数量 / Qty to load` styled as column J and summed in the 合计 row. Golden test on `2026-7-27  库存明细.xlsx` (committed under `documentation/plans/scm/fixtures/`).
- **AC-D2** A requested product absent from their list is appended below the last family with its own continuing 序号 and 备注 "不在库存表 / Not on your list", in the same styling.
- **AC-D3** A 0 ask leaves K empty (AC-C3 of part 3 stands); set lines print the supplier's code (AC-F12.6 stands).
- **AC-D4** The PDF renders the same 10+1 columns with the same merges (rowSpan), fills and fonts, A4 landscape, the title row first, the header row repeated on every page (`thead`) and no row split across a page (`page-break-inside: avoid` per row, which replaces the "one break per ~35 rows" wording: the row height is the supplier's, not ours, so a fixed count would split a family on the first tall row).
- **AC-D5** The public link page renders the same table (rowSpan merges, yellow fills, 合计 row) with the bilingual labels as a second header line; no prices, no navigation (AC-C6 of part 3 stands).
- **AC-D6** Without a retained file the document has the same 10+1 header, no merges, 商标 = company letter (blank on a set line, which carries no product id), 规格 = the supplier snapshot's spec when known (there is no size column on `products`), 品名 = product name; the five-column fallback no longer exists (pytest asserts the header of the no-file case).
- **AC-D7** One `SheetModel` feeds xlsx, PDF and the page (pytest: the three renderers are called with the same object; a change to the model changes all three).

## E. Proforma invoices list (S5)

- **AC-E1** Toolbar right cluster = [gear] [Start ▾]; Start opens "Upload proforma invoice" and "Convert N to packing list" (disabled with "Select invoices first" until rows are ticked).
- **AC-E2** Gear (`aria-label="More actions"`) holds Export and "Delete N" (destructive, AlertDialog, disabled without selection); the selection strip shows "N selected · Clear" only.
- **AC-E3** "Convert N to packing list" runs at once: no dialog; on success a toast "Packing list PL-2608-003 created with M lines" and navigation to it; skipped invoices named in the toast.
- **AC-E4** When the placement exceeds capacity, the `OverCapacityDialog` appears with the figures and a required reason; "Convert anyway" completes the conversion.
- **AC-E5** The strings "draft shipment" / "Convert N to draft shipment" appear nowhere on the PI list; the PI detail keeps its Convert with the line-quantity editor; "Add to existing draft" and `target_shipment_id` exist nowhere (list, detail, API).

## F. Packing list (S6)

- **AC-F1** A packing list created by convert or by `/new` without a number reads `PL-YYMM-NNN` (`PL-2608-001`, next `PL-2608-002`); the number stays editable on Details. Migration 440 seeds the rule from the shared definition in `app/services/numbering_defaults.py` (`bootstrap_env` + the test `after_create` hook replay it), and a company created after that migration ran has its series created on the spot by the convert rather than a 500; pytest asserts two conversions in one month increment, a company with no rule numbering `PL-YYMM-001` then `-002`, and that the random-hex path no longer exists (the service raises `numbering_rule_missing` only for a rule that exists and is disabled).
- **AC-F2** A converted packing list's Notes field is empty; the Proforma invoices tab and the Timeline carry the provenance.
- **AC-F3** An over-capacity conversion writes a Timeline entry "Converted over capacity: <figures>. Reason: <text>"; Notes stays empty.
- **AC-F4** Every supplier select on packing-list screens (Details, `/new`, per-line factory) and the PI detail shows the supplier NAME only; typing a supplier code still finds it.
- **AC-F5** On `/procurement-management/packing-lists/{id}/lines`, gear > Edit keeps the URL on `/lines`, the lines become editable in place, and Save / Cancel keep the URL; same on Details. The jump did not reproduce at the branch point (part 3's routed-tab record had already fixed it); the run is recorded and a regression guard covers Edit / Cancel / Save.
- **AC-F6** The downloaded packing list contains only the shipment's lines: no "Not packed - loading plan asked N" rows, no "Not on the loading plan" or "Loading plan asked X, packed Y" remarks; REMARKS = the line's own remarks.
- **AC-F7** Fidelity test on `FSCU8103365.xlsx` (committed fixture): a shipment built from that file exports a workbook whose header block (A1:B12 labels, date formats `dd/mm/yyyy`), column header rows 15-16 (labels, merges), column widths, row heights (data 35.1, subtotal 15.95), fonts (Calibri 12; bold header; bold red subtotal), number formats (`0.00;[Red]0.00` L/M, `#,##0.00` U), formulas per line, V-column block amount merged down each block, the `-` rule row, the SORENTO/MOCHA footer and the 订单号/柜号/封号 rows match the reference cell by cell (allowing for the shipment's own values).

## G. SPO planner (S7)

- **AC-G1** Clicking PO covers opens a Dialog listing PO candidates (issue date ASC) with a checkbox each, the suggested takes pre-ticked, the qty taken per row and a footer "n of m POs · covers X of packed Y"; unticking lowers the cell and the SPO-qty clamp exactly as the old popover did.
- **AC-G2** Clicking SO covered opens a Dialog listing open demand lines (Sales order, Customer, Class, Required, Open, Take, Location), project first then retail, pre-ticked to the packed quantity, with an "Unassigned N" footer; ticks feed the split as today.
- **AC-G3** Clicking On hand opens the location Dialog (site pools first, sum = cell); clicking Incoming SPO opens the SPO Dialog (rows sum = cell).
- **AC-G4** Each line has a chevron; the expanded row, full width, shows destination rows (warehouse select, qty, remove), an Unassigned row that turns destructive when the split exceeds the SPO qty and "Add location" (no coverage list in the row: that is the SO covered dialog); the Location cell reads "No location" / `BRW` / "3 locations" with "N unassigned" beneath.
- **AC-G5** Expand all / Collapse all on the toolbar expand and collapse every line.
- **AC-G6** No `Popover` remains in `SpoPlannerTable.tsx`; `LocationSplitPopover`, `PoTakesDrillPopover`, `SoCoverageDrillPopover` are deleted; `SpoPlannerTable.test.tsx` covers the four dialogs and the expanded row.
- **AC-G7** Create SPO, the split validation (`splitMismatch`, `overTicked`), the footer count and the Schedule view are unchanged (existing tests stay green).

## H. Guards

- **AC-H1** Rank, Suggested qty formula, Outstanding / BRW On Hand / From SPO / To request cards, the schedule view and the unmatched-codes queue behave as in part 3 on a plan opened from the list.
- **AC-H2** Existing supplier-request public pages for tokens issued before 441 still render (columns default to the no-file model).
- **AC-H3** `tests/scm` failures on the branch equal the base's pre-existing set (bisect note in the PR).
- **AC-H4** Single alembic head after the last migration on the lane; dev DB DDL applied via `Operations.context`, `alembic_version` untouched.
