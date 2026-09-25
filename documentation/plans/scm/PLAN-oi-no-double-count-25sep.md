# PLAN: Order inquiry view without double counting - one row per sales order line, history behind the History icon

Status: DRAFT, pending the owner's grill (G1-G10 below, posted on the docs PR). No code until the
owner rules. Track: feature (three-phase) - expected diff is over ~300 lines across FE and BE; no
migration, no auth/RBAC change, no new ingest surface, so `security-reviewer` is expected to be
skipped. Issue #1248. Docs branch `claude/oi-no-double-count-plan-kyf2l4` (draft PR; docs PRs are
never merged alone, this plan rides in the first feature PR).
UAC: `oi-no-double-count-25sep-acceptance-criteria.md`
Mockups: `mockups/oi-no-double-count-25sep.html` (inquiry detail at 1280 and 375, before and after,
plus the History dialog)
Domain: scm (Project Sales > Order Inquiries, `/project-sales/order-inquiries/<id>`, Lines tab)
Sits on: #1220 (`fix/oi-links-24sep`, `PLAN-oi-links-autocount-truth-24sep.md`) and #1244
(`feat/oi-decision-trail-ui`, `PLAN-oi-decision-trail-ui.md`). Both are open and both are based on
main, not on each other. This lane starts after both merge (see "Conflicts").

## Why

Owner, 25 Sep 2026 (verbatim in #1248): "there will be no double counting in the UI, if we
redirect, the UI will show it is 'used' and spawn a new line in the OI form view, which will be
confusing, i mean the OI row can retain in the data but I want to do until like what we show in
OI, don't have double counting, tally with sales order that it is flown from, but the used line or
whatever line that we use for logging purpose and tracking purpose, can be viewed by me in a way,
so we need to design the OI surrounding this principle: it should not look double count and
should look similar to sales order lines".

Three principles, binding (from the issue):

1. The inquiry view never looks double counted: one visible row per sales order line, quantities
   that tally with the sales order it flows from.
2. The visible rows look and read like sales order lines.
3. Rows kept for logging and tracking (used, superseded, cancelled, re-raised) stay in the data
   and are reachable by the owner in a separate view, not in the main row list.

The owner's standing instruction on simplicity applies (brief: "R22 - every screen as simple and
guided as possible, information overload is a defect"). Note: no committed plan carries an
order-inquiry ruling numbered R22; every R22 found in `documentation/` belongs to another plan.
It is cited here from the brief and should be confirmed or renumbered by the owner.

## Journey (step 1 - before any table, endpoint or state is named)

Actor: the owner or a purchasing user reading one order inquiry. Frequency: tens of times a day
for purchasing, a few times a day for the owner.

1. **Arrives** from the Order Inquiries list (header row click) or from the sales order's
   "Order inquiry" cell (`SalesOrderDetail.tsx:1128-1168`), which already names ONE inquiry per
   sales order line.
2. **First screen** is the inquiry's Lines tab. It reads like the sales order's Lines grid: one
   row per sales order line, in the sales order's own line order (No. 1, 2, 3...), the same
   product, the same Qty the sales order shows, then what purchasing has to do about it (Buy, the
   PO / SPO it sits on, State). The row count equals the sales order's line count on this
   inquiry; the Qty column foots to the sales order's own Qty for those lines.
3. **What the system already knows** and never asks: which rows belong to which sales order line
   (`order_inquiry_rows.so_line_id`), which are live and which are history (`state`,
   `redirected_to_pool`, `line_cancelled`), what replaced what (the note and `previous_qty`
   already written at raise time).
4. **One decision per step.** Purchasing ticks lines (not rows) and presses Confirm (N), exactly
   as today; Link selected (#1220) works on the ticked lines' live rows.
5. **When a line changed after its PO was received** (the #1248 case): the line still shows ONE
   row, carrying the current need. The State cell reads "To confirm" with the Was / Now the
   handshake already carries ("Was 2, now 5"), so purchasing sees that it moved without seeing a
   second row.
6. **History, when asked for.** The History icon already in the row's State cell (#1244) opens
   one dialog for that sales order line. Its Rows tab lists every retired row of the line (used,
   superseded, cancelled, re-raised, cancel-balance), newest first, each with its qty, the
   document it sat on and the reason already written in its note. Its Decisions tab is the #1244
   decision trail, unchanged. Reserve history (today's separate History icon on reserved rows)
   becomes its third tab when the line has any.
7. **At the end** the reader holds one row per line whose numbers tally with the sales order, and
   a one-click trail for any line they doubt.
8. **Nobody else is told anything new.** No notification, no email change. The handover email,
   the board and reorder planning read rows, not this view, and are unchanged.

## Row lifecycle (every state a row can be in, what it flows from, what the owner sees)

Every row carries `so_line_id` (FK `projects.sales_order_lines.id`, `project_so.py:1007`). No row
links to the row that replaced it; the relation lives only in `note` plus
`previous_qty` / `previous_delivery_date` (`project_order_inquiry_service.py:1368-1389`).

| # | Row state (how it is encoded) | Written by (service file:line) | Flows from the SO line as | Today on the detail | Under this plan |
|---|---|---|---|---|---|
| L1 | Live ORDER / ORDER_BACK, `raised` | re-raise in `refresh_for_decision` 1336-1439 (`qty = need - placed`) | the line's current buy need | own row, "To buy" | folded into the line row: counts in Buy |
| L2 | Live, `partly_linked` / `placed` | `refresh_link_state` / `_coverage_state` 5925, 5981-5991 | part or all of the need, on a PO / SPO | own row | folded: counts in Buy; its documents show in PO / SPO |
| L3 | Live, `actioned` | `mark_rows` 5319, import 2834 | need purchasing marked done | own row, "Done" | folded: counts in Buy |
| L4 | Draft (cascade-only links) | `_cascade_only` 1052-1060; after #1220 these become `order_inquiry_suggested_links`, not links | a proposal for the need | own row with a draft link | folded; the proposal shows in #1220's Suggested column |
| L5 | Settled in place (same row, `previous_qty`, ack `changed`) | `_settle_row_in_place` 1595-1794 | the line's changed need, same row | one row, Was / Now | unchanged: one row, Was / Now in State |
| L6 | Used: `redirected_to_pool = true`, state kept | `_redirect_row_if_received` 2058-2137 | a need whose PO / SPO was received into stock and released at a replan | own row beside its replacement, "used" pill (`orderInquiryWorklistColumns.tsx:574-593, 662-672`) | **History only** (Rows tab, "Used"). Out of Buy and header totals |
| L7 | Replacement of a used row: fresh L1 with note "Replaces N used; ..." | 1368-1389 | the line's current need after the redirect | own row, beside L6 | the line row; Was / Now reads the used qty (already `previous_qty`) |
| L8 | Superseded: `cancelled`, note "Superseded by revision N" | supersede loop 1208-1228; local origin 928-964; `_retire_settled_cancel_balance` 3521; `_retire_uncovered_rows` 3691-3832 | an earlier revision's instruction for the line | hidden (client filter `OrderInquiryLinesTab.tsx:142`) | History only ("Superseded") |
| L9 | Re-raised carry: old row `cancelled`, fresh row inherits the handshake | carry site 1390-1439 (#1233) | the same need moved under the new revision | old hidden, new visible | History only for the old ("Re-raised"); new is the line row |
| L10 | Shrunk partly_linked, note "Remainder superseded by revision N" + a fresh L1 for the rest | netting loop 1251-1301 | need split: linked part + fresh remainder | TWO live rows | **folded** into ONE line row (Buy = both); the note goes to History |
| L11 | CANCEL_BALANCE (`placed > need`) | 1440-1474 | over-cover to cancel on the PO | own row | folded into the line row as a State hint ("Cancel 2 on PO"), never added to Buy (G5) |
| L12 | DELAY / ADVANCE / CHANGE_SO sibling rows | `_stamp_date_move` 1796-1930 and planning-change | a date instruction for the line | own row each | folded: the line's State carries the instruction; no qty added |
| L13 | Rows on a cancelled SO line (`line_cancelled`) | `flag_rows_for_cancelled_lines` 478 | the line was cancelled on the SO | own row, "cancelled" pill, not greyed on the detail | one grey line row "Line cancelled", Buy 0, until confirmed; then History (G7) |
| L14 | ORDER_BACK donor-hole rows | `_raise_borrow_shortfalls` 3564-3689 | the borrowing line (qty belongs to the donor location) | own row | folded under its `so_line_id` like L1; the donor location shows in Location |
| L15 | Sheet split rows (364 + 364 on one 728 line, measured SO314594 C-FH12) | sheet import | one line split across rows | two rows | folded: one row 728 |
| L16 | Amendment-header rows (own `order_inquiry_id`) | `derive_for_amendment` 3869-4069 | the same SO line under another header | on the other header's detail | unchanged (they are another inquiry); out of scope, see Open |
| L17 | Rows with null `so_line_id` | some ORDER_BACK / amendment rows | no SO line | own row | stay one row each (a line of their own) |

## Measured facts: every place the OI UI renders more than one row for one SO line

Paths under `sorento_crm_frontend/app/(protected)/project-sales/` unless stated; origin/main
`76ade0ac`, 25 Sep 2026.

| # | Site | file:line | What makes the second row |
|---|---|---|---|
| D1 | Inquiry detail, Lines tab | `order-inquiries/[id]/components/OrderInquiryLinesTab.tsx:139-145` (filter), grid 184-237 | only `state !== 'cancelled'` is removed; every live, used, cancelled-line, sibling-verb and split row is its own grid row |
| D2 | Inquiry detail selection / Confirm / Link selected | `order-inquiries/[id]/components/OrderInquiryDetail.tsx:212-215` (`activeLines`) | selection is per row, so a used row can be ticked and confirmed next to its replacement |
| D3 | Used-row pill and dialog | `order-inquiries/components/orderInquiryWorklistColumns.tsx:574-593, 662-672`; `OrderInquiryQtyAnnotationDialog.tsx:51-81` | the used row stays in the grid with a "used" pill; the detail does not even grey it (`OrderInquiryLinesTab.tsx:198`) |
| D4 | Worklist (all inquiries) | `order-inquiries/components/OrderInquiriesClient.tsx:1869-1873` (grey only), State filter 1308-1325 | used and cancelled-line rows listed, greyed; cancelled rows back on State filter |
| D5 | Header list Lines / Qty | `order-inquiries/components/OrderInquiryHeadersList.tsx:320-335`; BE `sorento_crm_backend/app/services/order_inquiry_header_service.py:171-181` | `count(rows)` and `sum(qty)` over non-cancelled rows, used included: a 220 line with a used 182 reads 2 lines, 402 |
| D6 | Per-project order inquiry list | `[projectId]/order-inquiries/components/OrderInquiryClient.tsx:56, 81, 131-336` | every row, cancelled included unless filtered; Revision column per row |
| D7 | Matrix and calendar drilldowns | `OrderInquiryMatrixCellDrilldown.tsx`; `orderInquiryWorklistColumns.tsx:836-842` | reuse the row-level worklist columns |
| D8 | PO / SPO lightbox "Allocated to" | `order-inquiries/components/OrderInquiryDocumentDialog.tsx:163-215` | one line per link, so a line with two rows on the same PO appears twice |
| D9 | Worklist and inquiry exports | `_shared/hooks/useOrderInquiry.ts:248`; `OrderInquiriesClient.tsx:1120-1127` | server-built, row-level; same duplicates |
| D10 | Legacy SO order inquiry read | BE `GET /sales-orders/{pso_id}/order-inquiry` (`api/v1/projects/order_inquiries.py:1099` -> service 5287) | every row of the latest header, cancelled included, with `decision_revision` |

Not a duplicate: the sales order's own "Order inquiry" cell (`SalesOrderDetail.tsx:1128-1168`)
already shows one inquiry per line; bundled companions (`orderInquiryWorklistColumns.tsx:544-566`)
are other lines' rows.

## Grill (step 2) - questions for the owner, recommendation first

| # | Question | Recommended answer | Trade-off |
|---|---|---|---|
| G1 | A line the confirmation names changes after its PO was received (the #1248 case: "Replaces 2 used"). What does the main view show? | ONE row with the line's current need (today's fresh row qty, which already nets everything still placed; received goods that still serve the line are netted by the existing own-arrival credit, Path B, `_redirect_row_if_received` 2101-2106). The used row moves to History. State reads To confirm with "Was 2, now 5". **The data does not change**: no new netting rule on the fresh row. | Netting the received 2 into the fresh row (raise 3, not 5) would read tighter, but it reverses `PLAN-oi-replan-received-links.md` ("a fully received document does not carry a row through a replan"): the goods were released to the pool and other demand may take them, so the line would under-buy. Presentation only is reversible; a data rule is not. |
| G2 | Is the history view per row, per inquiry, or per sales order? | **Per sales order line**, opened from the line row's History icon. That is the grain the owner asks about ("where did this line's numbers come from") and the grain #1244's decision trail already uses (`core_line_id`). No inquiry-level or SO-level history page. | Per inquiry would show every retired row of every line in one list: complete, but it is the overload the owner is removing. Per row does not exist any more once rows fold. |
| G3 | One History icon or several? Today the State cell can carry the reserve History icon (`orderInquiryHeaderLinesColumns.tsx:165-176`) and #1244 adds the decision-trail icon beside it. | **One** icon, one dialog, line tabs: Rows (retired rows), Decisions (#1244 trail), Reserve (only when the line has reserve history). | Three separate icons keep each dialog simple but make the row noisy and ask the reader which history they want. One dialog with tabs asks nothing up front. |
| G4 | Which quantities does the line row show so it tallies with the sales order? | Two: **Qty** (the sales order line's own Qty, same number the SO grid shows) and **Buy** (sum of the line's live buy rows). When Buy is lower, its cell carries a hover "3 from stock". Header card foots Buy. | A third "From stock" column tallies explicitly (Qty = From stock + Buy) but adds a column to every row for the minority of lines that reserve. |
| G5 | A line with more than one LIVE row (L10 remainder + fresh, L12 DELAY / ADVANCE, L15 sheet split, L11 cancel-balance). | **Fold** into the one line row: Buy = sum of live buy rows, PO / SPO show every document ("PO-0031 +1"), State shows the most urgent instruction. The existing expand chevron shows the parts when needed. CANCEL_BALANCE is never added to Buy. | Showing them as indented child rows is more literal but brings back two rows per line. |
| G6 | Owner ruling C2 (`PLAN-oi-cancelled-line-used-confirm.md`) keeps a confirmed used / cancelled-line row "listed, grey and tagged". Reverse it? | **Yes, reverse C2 for the detail and the worklist.** A used row's To confirm (C3) rides on the line row (its replacement is already `changed` with Was / Now). Confirming the line acknowledges the line's used rows in the same call, so the header never sits Outstanding on a row nobody can see. | Keeping C2 keeps a visible audit on the main screen, which is exactly the double count #1248 removes. The audit moves to History, nothing is deleted. |
| G7 | A cancelled sales order line (L13). | One grey row, "Line cancelled", Buy 0, until confirmed (C1 stays: it is news). After Confirm it stays as one grey row, like the SO grid still shows a cancelled line; its rows are in History. | Dropping it from the view after Confirm tallies with an SO that hides cancelled lines, but the SO grid does not hide them. |
| G8 | Does the rule apply to the Order Inquiries worklist (all inquiries) as well as the detail? | **Yes, second slice**: used and confirmed cancelled-line rows leave the worklist by default; a "History" choice on the State filter brings them back (it already does this for cancelled). Row-per-line folding is detail-only; the worklist stays one row per instruction so purchasing's filters keep working. | Folding the worklist too is fully consistent, but the worklist's per-supplier and per-PO filters are row-level and would need rework. |
| G9 | Does the row model need a `superseded_by` link? | **No, not in this lane.** Grouping by `so_line_id` already puts every row of a line together; the note, `previous_qty` and `created_at` already say what replaced what. Trigger for the column, named: the History tab has to pair an old row with its replacement ACROSS lines (planning-change reallocation, `planning_change_service` ~3629) or across headers (amendment rows, L16). | A link column would let the Rows tab draw "replaced by" arrows, at the cost of a migration and a write at every supersede site, all of which #1220 also edits. |
| G10 | Header list Lines / Qty (D5). | Lines = distinct sales order lines with a live row; Qty = sum of live buy rows (used excluded). Same numbers the detail foots. | None real; today's numbers contradict the detail. |

## Design

### The line row (Lines tab)

Columns, in the sales order Lines grid's order (`SalesOrderDetail.tsx:689-1290`: No., Product,
Qty ..., Location, Delivery date, Status), then the inquiry's own:

Select, **No.** (SO line_no), Product (code only, R7 of `PLAN-oi-header-list-detail.md`), **Qty**
(SO line), **Buy**, Delivery date, Location, Supplier, PO, SPO, Suggested (#1220), Instruction,
State (pill + the one History icon). "Raised via" (#1244) stays hidden by default and reads the
line's current live row. The SO line cell (`SO402757 · L5`) is dropped from the detail: the
header already names the sales order and No. is the line.

Sorted by No. Rows with no `so_line_id` (L17) sort last as lines of their own.

Fold rule (G5), pure and client-side: group the inquiry's rows by `so_line_id`; a group's live
rows are `state != 'cancelled' and not redirected_to_pool`; history rows are the rest. A line
whose group has no live row and is not `line_cancelled` renders as one grey row, Buy 0, State
"Nothing to buy", with its History icon, so the line count still tallies with the sales order
(Open O2 asks the owner to confirm this on the mock).

### History dialog (G2, G3)

Extends `DecisionTrailDialog` (#1244) rather than adding a component: title "History - <item>
(<SO> L<n>)", `TabsList variant="line"`: Rows | Decisions | Reserve. Rows is a small `DataGrid`
(fixed layout, explicit sizes, truncate + title): When, Qty, What (Used / Superseded / Re-raised /
Cancelled / Cancel balance / Line cancelled, `Badge` pill), Document (PO / SPO links as they
stood), Why (the row's note). Newest first; the live row on top as "Now" so the reader sees what
the history leads to. Empty: "No earlier rows for this line." Reserve tab only when the line has
reserve history (today's `ReserveLineHistoryDialog` body moves in, its icon goes).

Motion: the dialog uses the standard lightbox surface spring; nothing else animates. No motion on
the fold, the row, the tabs switch (tens a day: none), or the History icon.

### Backend seam - presentation plus two read fixes, no migration

- The Lines tab fetch (`orderInquiryService.ts:883-907`, worklist endpoint with `inquiry_id`)
  gains `include_history=true`, which returns cancelled rows too (today they need
  `state=cancelled`, worklist service 1208-1214). The FE partitions.
- `OrderInquiryWorklistRow` gains `so_line_qty` (SO line Qty as the SO grid shows it) and
  `so_line_no`; both declared on the schema and asserted by name (response_model drops undeclared
  fields).
- Header counts (`order_inquiry_header_service.py:171-181`): `lines_total` = distinct `so_line_id`
  over live rows (null `so_line_id` counts each row), `qty_total` = sum of live buy rows with
  `redirected_to_pool = false`, `lines_to_confirm` = distinct lines with a live or used row in
  `awaiting` / `changed`.
- Confirm (G6): confirming a line's live rows also acknowledges that line's `redirected_to_pool`
  rows in `changed` on the same header, in the same transaction.
- No `superseded_by` column (G9). No alembic revision, so no fight with #1220's `oisl_0001`.

## Slices

| Slice | Phase | What | Blocks |
|---|---|---|---|
| S0 | 1 (FE mock) | Lines tab folds by `so_line_id` from today's payload, No. / Qty / Buy columns (mocked `so_line_qty`), selection per line, one History icon + tabbed dialog with the Rows tab built from rows already loaded plus a mocked cancelled set. Owner hands-on on :3000 | S1 |
| S1 | 2 (BE, tester first) | `include_history`, `so_line_qty` / `so_line_no`, header counts, Confirm sweeps used rows | S2 |
| S2 | 2 (FE wire) | swap mocks for the real fields; header list reads the new counts; Link selected (#1220) maps lines to live row ids | S3 |
| S3 | 2 | Worklist: used and confirmed cancelled-line rows hidden by default, State filter "History" (G8) | - |
| S4 | 3 | reviewer + browser pass at 1280 and 375 (sidebar navigation from `/`), DoD gate, one PR | - |

## Conflicts with #1220 and #1244 (land this lane after both)

- `OrderInquiryDetail.tsx`: #1220 rewrote selection and Link selected around `activeLines`
  (main :213). S0 replaces `activeLines` with line groups; rebase onto #1220's version.
- `orderInquiryHeaderLinesColumns.tsx`: #1220 adds Suggested; #1244 puts `DecisionTrailButton`
  in the State cell (~:388-411) next to the reserve History icon (:165-176). G3 merges both
  icons into one; the reserve icon and `ReserveLineHistoryDialog` are removed.
- `OrderInquiryLinesTab.tsx`: #1244 adds `initialState.columnVisibility`
  (`DEFAULT_HIDDEN_COLUMNS = ['inquiry_no','raise_event']`) beside the row filter this lane
  replaces.
- `DecisionTrailDialog.tsx` / `DecisionTrailButton.tsx` (#1244): extended with tabs, not forked.
  The button today returns null without `core_line_id`; a line row with only retired rows or a
  null-line row still needs the icon, so the gate moves to "has core line or has history".
- `schemas/project_order_inquiry.py` `OrderInquiryWorklistRow` and
  `order_inquiry_worklist_service.py` serializer (~:2199 / :2317): #1220 adds `suggested_links`,
  #1244 adds `raise_event_*`; S1 adds `so_line_qty` / `so_line_no` at the same spot.
- `orderInquiry.types.ts`: all three add fields.
- `decision_trail_service._raise_entries` (#1244) matches rows to raise events by `created_at`; a
  replacement row reads as a fresh raise there. The Rows tab explains it; no change to #1244's
  service.
- Alembic: none from this lane. #1220's `oisl_0001` re-parents onto main on its own.
- Standing rulings this plan asks the owner to change: C2 (`PLAN-oi-cancelled-line-used-confirm.md`)
  and the 17 Sep "greyed with ONE one-word `used` mark on the Qty cell" ruling
  (`PLAN-oi-replan-received-links.md`). Both move from the main view into History; neither loses
  data.

## Open

- O1: amendment-header rows (L16) for the same SO line live on another inquiry. Should the History
  Rows tab list them too (by `so_line_id` across headers)? Default: no, this inquiry only.
- O2: a line whose rows are all retired (fully served by stock after a redirect) renders nothing
  on the detail. Alternative: one grey row "Nothing to buy" with History. Default in S0: render
  the grey row, so the SO line count still tallies; confirm with the owner on the mock.
- O3: exports (D9) and the PO / SPO lightbox (D8) stay row-level. Named as follow-ups if the owner
  hits them.

## Out of scope

Any change to how rows are written (redirect, settle, netting, supersede); the board; reorder
planning; the handover email; the per-project order inquiry list (D6, legacy); `superseded_by`.
