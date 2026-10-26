# PLAN: OI purchasing email + Excel show only what purchasing must act on

Status: Build done, under review (owner answered the card 26 Oct ~13:05). Track: small fix (no
migration, no auth/RBAC, no new ingest).

## 0. Owner rulings, 26 Oct 2026 ~13:05 MYT

Verbatim: "Local buy dont need go purchasing, 1a, 2 same as now, 3 not sent, 4 same as now show
use own location, if we say cancel order, the purchasing will think it is customer cancel order,
so need to mention change from buy to use own location, 5a".

- Rule 2 change: LOCAL BUY is NOT sent to purchasing.
- Q1 (a): a mixed line reads only purchasing's part, `ORDER 4`; QTY stays the line's 10.
- Q2: Cancel SO keeps today's behaviour: `record_cancelled_lines` (S:5058) queues ONE `CANCEL`
  line for every line transferred to Cancel SO, whatever it held, so a line purchasing never
  held anything for is still told. Unchanged.
- Q3 (a): Use incoming (SPO no.) and Borrow incoming lines are not sent.
- Q4: the line is still sent, but its REMARK states the change instead of today's
  `USE <loc>, CANCEL ORDER n` (S:5193-5200, pinned by `test_a_buy_replaced_by_stock_says_to_
  take_the_order_back`), which purchasing reads as a customer cancel. New wording:
  `CHANGED: ORDER 10 -> USE BRW-BB 10` (each side's parts with their quantities).
- Q5 (a): exactly rule 4's columns.

Lane: OI-EMAIL-PURCHASING-FOCUS. Owner ask 26 Oct 2026 ~12:45 MYT. Supersedes the "every saved
decision is listed" part of the 13 Oct 22:40 ruling (`saved_line_remark` docstring).

Files: S = `sorento_crm_backend/app/services/project_order_inquiry_service.py`,
W = `sorento_crm_backend/app/services/order_inquiry_worklist_service.py`,
R = `sorento_crm_backend/app/services/oi_handover_resend.py`.

## 1. Where the rows come from today (two sources, which is the defect)

- Email rows: the Confirm's handover queue (`db.info["oi_handover_pending"]`). Each saved line
  is queued by `record_saved_lines` (S:4593) / `_queue_saved_line` (S:5108), one line per saved
  line whose decision is new or changed. A Cancel SO line is queued by `record_cancelled_lines`
  (S:5058) as REMARK `CANCEL`, QTY = what was owed, QTY CHANGE TO 0. The drain
  (`_fire_pending_handover`, S:~14574) hands the queue to `build_handover_email` (S:14269), which
  builds `handover.lines` in `_build_handover_context` (S:14015).
- Excel rows: `store_handover_excel` (S:14219) calls
  `OrderInquiryWorklistService.export_xlsx(inquiry_id=...)` (W:3495). On a Confirm it passes NO
  `row_ids` (S:14305), so the workbook is the WHOLE OI: every row of the order that is not
  `cancelled` (W:1374), whatever this Confirm decided. The resend passes the open rows it emailed
  (R:340-341), so it is closer, but it is still OI rows, not the email's lines (a saved line, a
  split row, a Cancel SO line are not OI rows).
- Why a cancel-all differs (SO394881 shape, `PLAN-batch-held-cancel-21oct.md`: 10 book-cancelled
  lines + 12 lines transferred to Cancel SO + the covered rest): the email lists the 12 `CANCEL`
  lines; the cancel turns their OI rows `cancelled`, and W:1374 drops cancelled rows, so the Excel
  shows the rest of the order's open rows and none of the 12. The two sets are disjoint.
- Columns today: the email line table is LOCATION | ITEM CODE | [NEW ITEM CODE] | QTY | [QTY
  CHANGE TO] | DELIVERY DATE | [DELIVERY DATE CHANGE TO] | REMARK, change columns only when a
  line has one (`oihr_0008_so_table_on_top.py`, `oihr_0007_excel_remark.py:60-97`); the S/O facts
  print once in a table above. The Excel prints `EXPORT_HEADINGS` (W:195-239): 19 columns incl.
  REQUESTED RESERVE, RESERVED, TOTAL QTY, ACKNOWLEDGED, TAKEN, REMAINING, SUGGESTED, SUPPLIER,
  PO NO.

Dev data: this lane runs in a cloud sandbox with no access to the dev copy, so the SO394881
facts above are from the code path and the batch-held-cancel plan, not a live read. The hand
test script (section 6) compares the two on the crew copy.

## 2. Behaviour card

Rules:

1. ONE row source. The handover Excel is written from the email's own `handover.lines` (the list
   `_build_handover_context` returns), never from an OI query. Same rows, same order, same
   values. Confirm and resend both go through `build_handover_email` already, so both get it.
2. A line is sent to purchasing only when it carries something purchasing acts on: ORDER, ORDER
   BACK (Buy order back, and Borrow `ORDER BACK <donor>`), LOCAL BUY, CANCEL (Cancel SO), CANCEL
   ORDER n (an order purchasing held is taken back), or a qty / date / item-code change to a line
   purchasing held something for. A line whose decision is only "Use own location" (`USE <loc>`)
   or "Use BRW" (`USE BRW`) is not sent, and neither are its date/qty moves.
3. A Confirm whose lines are all filtered out by rule 2 sends no email (unchanged rule: notify
   only when there is an action).
4. Excel columns = the email's line columns plus the S/O facts per row: SO DATE | S/O NO | ITEM
   CODE | [NEW ITEM CODE] | QTY | [QTY CHANGE TO] | DELIVERY DATE | [DELIVERY DATE CHANGE TO] |
   PROJECT/CUSTOMER | LOCATION | REMARK. Bracketed columns only when a line in this email has
   one (as the email does). A new order is 8 columns. No REQUESTED RESERVE / RESERVED / TOTAL QTY.
   One sheet, house style (`excel_style.style_table`), as today.
5. The OI list page's own Export Excel and the planning-board worksheet are untouched.

Examples (shapes from code, values masked):

| Case | Email today | Excel today | Proposed (email = Excel) |
| --- | --- | --- | --- |
| A. SO394881 cancel-all: 12 lines to Cancel SO | 12 `CANCEL` lines | other open rows of the OI, none of the 12 | the 12 `CANCEL` lines (subject to Q2) |
| B. New SO, 3 lines: Buy 10, Use own location BRW-BB 6, Use BRW 4 | 3 lines: ORDER / USE BRW-BB / USE BRW | every OI row incl. reserve figures | 1 line: ORDER, QTY 10 |
| C. Mixed line: Use own BRW-BB 6 & Buy 4 | `USE BRW-BB 6 & ORDER 4` | the row with REQUESTED RESERVE 6 | 1 line, REMARK per Q1 |
| D. Amendment: Buy line 10 -> 8, date moved | `DELAY, CANCEL 2`, QTY 10 -> 8 | whole OI | that one line, with QTY CHANGE TO / DATE CHANGE TO columns |
| E. Re-approve with nothing changed | no email | none | no email (unchanged) |

Edge cases:

- Line was Buy, now Use own location: purchasing held an order, so it is sent as `CANCEL ORDER n`
  (Q4).
- Line was Use own location, now Buy: sent as ORDER (a fresh instruction, no "was").
- Split lines (`_tell_splits`): each printed split row is an email line, so it is an Excel row;
  a split whose only part is a USE reserve follows rule 2.
- A line purchasing never held, transferred to Cancel SO (Q2).
- The planner's own REMARK on a USE-only line: still not sent (it is about a reserve).
- Multi-SO email: S/O NO is per row in the Excel, since the email puts it in the SO table.

## 3. Questions (posted as crew-ask)

- Q1 Mixed line (Use own BRW-BB 6 & Buy 4): (a) send it, REMARK keeps only purchasing's part
  `ORDER 4`, QTY stays the line's 10; (b) send it as today, `USE BRW-BB 6 & ORDER 4`.
  Recommend (a): the owner said purchasing does not need the own-location part.
- Q2 Cancel SO on a line purchasing never held anything for (fully Use own / Use BRW): (a) not
  sent; (b) always sent as CANCEL. Recommend (a), same reason; a cancel-all of an order that had
  orders still lists those lines.
- Q3 Use incoming (SPO no.) and Borrow incoming (document no.) lines: (a) not sent, like Use own
  location (stock already on its way, nothing to order); (b) sent as today. LOCAL BUY stays sent
  either way. Recommend (a).
- Q4 A line that was Buy and is now Use own location: (a) sent as `CANCEL ORDER n` only;
  (b) not sent. Recommend (a): it changes a line purchasing already acted on.
- Q5 Excel columns: (a) exactly the email's columns + SO DATE / S/O NO / PROJECT/CUSTOMER per
  row (rule 4), no SUPPLIER / PO NO; (b) also SUPPLIER + PO NO so an amendment names the PO to
  change. Recommend (a): simplest, and the email has no PO either; (b) needs a PO lookup per
  saved line.

## 4. Build (as built)

- `purchasing_remark` / `_PURCHASING_KEYS` (S, beside `saved_line_remark`): a saved line's
  email REMARK keeps only ORDER / ORDER BACK parts. `_queue_saved_line` returns without a line
  when there is none and nothing purchasing held is taken back.
- Q4: `CHANGED: <before parts> -> <now parts>` only where stock replaced the order
  (`_stock_qty(now) > _stock_qty(before)`); other take-backs (a redirect, two rows folded, Buy
  turned Order back) keep today's `CANCEL ORDER n`.
- Planner's own REMARK on a line purchasing holds nothing for: not sent (`record_saved_lines`).
- `handover_xlsx(lines)` (W) writes the email's own `handover.lines` under `HANDOVER_HEADINGS`
  (change columns NEW ITEM CODE / NEW QTY / NEW DATE, the email's own words, only when a line
  has one); `store_handover_excel` stores it for Confirm and resend alike. The OI list export and
  the planning-board worksheet are untouched.
- `scripts/compare_oi_handover_email_excel.py <SO>`: the hand-test check, read-only.

Column words: the email's change columns read NEW ITEM CODE / NEW QTY / NEW DATE (oihr_0006 to
0010), so the Excel uses those words rather than "QTY CHANGE TO".

## 4a. Original build sketch

- `_build_handover_context` / `_queue_saved_line`: drop USE / USE_OWN parts per rule 2 + answers.
- New `handover_excel_bytes(context)` in W (or a small module) writing `handover.lines` with the
  rule-4 columns through `excel_style.style_table`; `store_handover_excel` stores it instead of
  calling `export_xlsx`. The resend stops passing `row_ids` (no longer needed).

## 5. Tests (red first)

- email rows == Excel rows for: new order (case B), amendment (case D), cancel-all (case A,
  SO394881-shaped fixture, masked names), resend of the same OI.
- USE-only Confirm sends no email (outbox empty).
- Excel headings: new order has no change columns and no reserve columns.

## 6. Hand test

Script compares, for one Confirm on the crew copy, the email's line table (outbox `body_html`)
with the stored Excel's rows; posted as `crew-handtest` after the build.
