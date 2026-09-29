# PLAN: Order inquiry view without double counting - one row per sales order line, history behind the History icon

Status: grilled (owner rulings 26 Sep 2026 folded in, see "Owner rulings 26 Sep 2026" below). S0
(FE mock) built on `feat/oi-no-double-count-s0` (PR #1266), owner hand-tested and approved 26 Sep.
S1 (backend, tester first, `tests/test_oi_no_double_count.py`) and S2 (FE wire, mocks removed)
built on the same branch, 26 Sep; browser evidence under `evidence/oi-no-double-count-s2/`. Owner
hand test of S1 + S2 (26 Sep ~11:20Z) asked for a line-level confirmed mark: fix round W1
(AC-ND-33) built on the same branch, evidence under `evidence/oi-no-double-count-w1/`. Fix
round 2 (26 Sep, the two reviewer passes on PR #1266): fold and count on the mirror line
`so_line_id` (review S1), one waiting-used-row rule for To confirm, the tick and the sweep
(review S2), tests for Unconfirm scope, the cross-pair sweep and `include_history` scope. S4
(owner pass on the stack) next. S3
(worklist) is dropped (G8). Track: feature (three-phase) - expected diff is over ~300 lines across FE and BE; no
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
Owner ruling 26 Sep: both are merged on main (`3ca359cf` #1220, `905d49f4` #1244); S0 branches
from main as it is now.

## Owner rulings 26 Sep 2026 (binding; verbatim answer on PR #1249, two answered in chat)

Every ruling below overrides the matching recommendation in "Grill"; the grill table is kept as
the record of what was asked.

- **G1** (verbatim: "actually all should just move to history, i don't even want to see was 2,
  now 5, very taxing"): every row that is not the line's current need moves to History,
  including the used row. The main view shows NO "Was 2, now 5" or any similar Was / now
  annotation: no Was text in State, no Qty (i) "Was" button on the line row. The Was / now
  story is read in History only (the Now row's note and `previous_qty`).
- **G2, G3, G9, O1, O2**: recommendations accepted as written. History is per sales order line;
  one icon, one dialog with Rows | Decisions | Reserve tabs, replacing both today's icons; no
  `superseded_by` link and no migration; amendment-header rows are not listed in History; an
  all-retired line shows one grey "Nothing to buy" row.
- **G4** (chat, verbatim: "we should have sales order line quantity, requested quantity from
  CS, then got the taken quantity, and the remaining qty, then is very clear"): the line row
  carries FOUR quantity columns, in this order: **SO Qty, Requested, Taken, Remaining**. They
  replace the plan's Qty / Buy pair; the "2 from stock" hover is dropped. Definitions in
  "The four quantity columns" below.
- **G5** (chat): always ONE row per sales order line, whatever the split: a 364 + 364 SPO split,
  6 on PO + 4 fresh, DELAY / ADVANCE rows and cancel-balance rows all fold into it. The PO / SPO
  cells list documents as "SPO-...0007 +1"; State shows the most urgent instruction; the pieces
  are listed in History.
- **G6** (verbatim: "actually all these should go to history right?"): used rows and confirmed
  cancelled-line rows go to History (C2 reversed).
- **G7** (verbatim: "yeah I am fine with showing cancelled lines as greyed, but used row should
  go to history"): a cancelled sales order line stays in the main view as one greyed row; its
  used rows still go to History.
- **G8** (verbatim: "it is fine, the worklist is going to discon soon, we always use the list
  view of the OI, then go inside to view rows"): no worklist change. Slice S3 is dropped.
- **G10** (verbatim: "The header list liens and qty should be truthful to what is shown in the
  Lines tab of form view"): the header list's Lines and Qty equal exactly what the form view's
  Lines tab shows: Lines = the number of line rows the Lines tab renders (unfiltered), Qty = the
  Lines tab's Requested footer total.
- **W1** (owner hand test of S1 + S2, 26 Sep ~11:20Z, chat, verbatim: "i just realized after we
  click confirm, at the line level can't really see it is confirmed, can we have an icon here to
  show it is confirmed?", the gap between Product and SO Qty boxed): each line row carries its
  own confirmation mark in a narrow column there. AC-ND-33 in the UAC.

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
   product, the same Qty the sales order shows, then what purchasing has to do about it (Requested, Taken, Remaining, the
   PO / SPO it sits on, State). The row count equals the sales order's line count on this
   inquiry; the Qty column foots to the sales order's own Qty for those lines.
   Owner ruling 26 Sep (G4): the quantities read SO Qty, Requested, Taken, Remaining, in that
   order; SO Qty foots to the sales order's own Qty for those lines.
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
   Owner ruling 26 Sep (G1): no "Was 2, now 5" on the main view. The State cell reads "To
   confirm" only; the used row and the Was / now story are in History.
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
| L1 | Live ORDER / ORDER_BACK, `raised` | re-raise in `refresh_for_decision` 1336-1439 (`qty = need - placed`) | the line's current buy need | own row, "To buy" | folded into the line row: counts in Requested, Taken, Remaining (Owner ruling 26 Sep, G4) |
| L2 | Live, `partly_linked` / `placed` | `refresh_link_state` / `_coverage_state` 5925, 5981-5991 | part or all of the need, on a PO / SPO | own row | folded: counts in Requested, Taken, Remaining (Owner ruling 26 Sep, G4); its documents show in PO / SPO |
| L3 | Live, `actioned` | `mark_rows` 5319, import 2834 | need purchasing marked done | own row, "Done" | folded: counts in Requested, Taken, Remaining (Owner ruling 26 Sep, G4) |
| L4 | Draft (cascade-only links) | `_cascade_only` 1052-1060; after #1220 these become `order_inquiry_suggested_links`, not links | a proposal for the need | own row with a draft link | folded; the proposal shows in #1220's Suggested column |
| L5 | Settled in place (same row, `previous_qty`, ack `changed`) | `_settle_row_in_place` 1595-1794 | the line's changed need, same row | one row, Was / Now | one row, State "To confirm"; Owner ruling 26 Sep (G1): no Was / Now on the main view, it reads in History |
| L6 | Used: `redirected_to_pool = true`, state kept | `_redirect_row_if_received` 2058-2137 | a need whose PO / SPO was received into stock and released at a replan | own row beside its replacement, "used" pill (`orderInquiryWorklistColumns.tsx:574-593, 662-672`) | **History only** (Rows tab, "Used"). Out of every quantity and the header totals |
| L7 | Replacement of a used row: fresh L1 with note "Replaces N used; ..." | 1368-1389 | the line's current need after the redirect | own row, beside L6 | the line row; Owner ruling 26 Sep (G1): no Was / Now on the main view, History's Now row carries it |
| L8 | Superseded: `cancelled`, note "Superseded by revision N" | supersede loop 1208-1228; local origin 928-964; `_retire_settled_cancel_balance` 3521; `_retire_uncovered_rows` 3691-3832 | an earlier revision's instruction for the line | hidden (client filter `OrderInquiryLinesTab.tsx:142`) | History only ("Superseded") |
| L9 | Re-raised carry: old row `cancelled`, fresh row inherits the handshake | carry site 1390-1439 (#1233) | the same need moved under the new revision | old hidden, new visible | History only for the old ("Re-raised"); new is the line row |
| L10 | Shrunk partly_linked, note "Remainder superseded by revision N" + a fresh L1 for the rest | netting loop 1251-1301 | need split: linked part + fresh remainder | TWO live rows | **folded** into ONE line row (Requested = both); the note goes to History |
| L11 | CANCEL_BALANCE (`placed > need`) | 1440-1474 | over-cover to cancel on the PO | own row | folded into the line row; its verb is the line's Instruction when it is the most urgent (G5), never added to Requested, Taken or Remaining |
| L12 | DELAY / ADVANCE / CHANGE_SO sibling rows | `_stamp_date_move` 1796-1930 and planning-change | a date instruction for the line | own row each | folded: the line's State carries the instruction; no qty added |
| L13 | Rows on a cancelled SO line (`line_cancelled`) | `flag_rows_for_cancelled_lines` 478 | the line was cancelled on the SO | own row, "cancelled" pill, not greyed on the detail | one grey line row "Line cancelled", Buy 0, until confirmed; then History (G7). Owner ruling 26 Sep (G7): the grey line row stays on the main view before and after Confirm; Requested 0, Remaining 0; its used rows go to History |
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

Owner rulings 26 Sep, per question (full text in "Owner rulings 26 Sep 2026" above):
G1 all non-current rows to History, no Was / now annotation on the main view; G2, G3, G9
accepted; G4 four columns SO Qty / Requested / Taken / Remaining; G5 always one row per line;
G6 used and confirmed cancelled-line rows to History; G7 cancelled line stays, greyed, its used
rows to History; G8 no worklist change, S3 dropped; G10 header Lines and Qty equal the Lines tab.

## Design

### The line row (Lines tab)

Owner ruling 26 Sep (G4, G5): columns, in the sales order Lines grid's order
(`SalesOrderDetail.tsx`: No., Product, Qty ..., Location, Delivery date, Status), then the
inquiry's own:

Expand (stock grid, as today), Select, **No.** (SO line_no), Product (code only, R7 of
`PLAN-oi-header-list-detail.md`), **SO Qty**, **Requested**, **Taken**, **Remaining**, Delivery
date, Supplier, PO, SPO, Suggested (#1220), Location, Instruction, State (pill + the one History
icon; reserve actions beside it as today). "Raised via" (#1244) stays hidden by default and
reads the line's primary row. The SO line cell (`SO402757 · L5`) is dropped from the detail: the
header already names the sales order and No. is the line. The Qty (i) "Was" button
(`QtyAnnotationButton`) does not render on a line row (G1).

Sorted by No. Rows whose line cannot be resolved (L17) sort last as lines of their own.

#### The four quantity columns (G4), against the existing row fields

A line's **live buy rows** are its rows with `isInquiryBuyRow(verb)` (ORDER, ORDER_BACK,
RESERVE_AND_ORDER, `_shared/lib/orderInquiryWorklist.ts`), `state != 'cancelled'` and
`redirected_to_pool` false. Notice rows (CANCEL_BALANCE, DELAY, ADVANCE, CHANGE_SO, ...) are
never in any quantity.

| Column | Definition | Today's field | S0 |
|---|---|---|---|
| SO Qty | the sales order line's own quantity, the number the sales order's Lines grid shows for that line | none on the worklist row; S1 adds `so_line_qty` | **mocked**: `so_line_qty` when present, else the line's Requested (marked `MOCK(S1)` in code) |
| Requested | what CS raised for purchasing to buy: sum of `qty` over the line's live buy rows | `qty` | real |
| Taken | sum over the same rows of `linked_qty + reserved_qty` (the existing per-row Taken, `inquiryRowTaken`) | `linked_qty`, `reserved_qty` | real |
| Remaining | Requested minus Taken minus the rows' `bundled_qty`, never negative (the existing per-row Remaining rule, summed per line) | `bundled_qty` | real |

A cancelled sales order line (`line_cancelled`, G7) reads SO Qty as the SO shows it,
Requested 0 and Remaining 0 (called off, not owed), Taken as its live rows still hold. A line
with no live buy row (O2) reads Requested 0, Taken 0, Remaining 0.

Footer totals, over the rendered line rows minus cancelled lines: SO Qty, Requested, Taken each
a plain sum; Remaining = Requested - Taken - bundled (the existing `inquiryFooterTotals` rule).

#### Fold rule (G5), pure and client-side

Group the inquiry's rows by sales order line. The worklist row carries no `so_line_id`; it
carries `core_line_id` (the core line resolved from the row's mirror `so_line_id`, one-to-one)
and `line_no`. Fold key: `core_line_id`, else `so_number` + `line_no`, else the row's own id (a
line of its own). A group's live rows are `state != 'cancelled'` and not `redirected_to_pool`;
its history rows are the rest.

- The line's **primary row** is its most urgent live buy row, else its first live row. It
  addresses the reserve actions, Raised via, Delivery date, Supplier and Location.
- **State** = the most urgent live state: raised (To buy) > partly_linked > placed > actioned; a
  live row's reserve state (requested > reserved > declined) wins over the plain state pill.
  `line_cancelled` reads "Line cancelled"; no live row reads "Nothing to buy".
- **Instruction** = the most urgent live instruction: CANCEL_BALANCE > CHANGE_SO > DELAY >
  ADVANCE > the primary row's verb.
- **PO / SPO** = every document across the live rows, deduplicated, in row order: the first as
  today's link, then a "+N" chip that opens a popover listing all of them.
- A cancelled line and a line with no live row render grey.

Selection is per line: ticking a line selects all of its live rows; Confirm (N) counts lines; a
line with no live row cannot be ticked. Confirm, Unconfirm and Link selected keep sending row ids
(the ticked lines' live row ids). Owner ruling 26 Sep (G6): Confirm also sends the ticked lines'
used rows still in `changed`, so the header never waits on a row nobody can see (S0 does this
client-side by id; S1 moves it server-side for the whole-OI Confirm).

### History dialog (G2, G3)

Reuses #1244's trail rather than forking it: `DecisionTrailDialog`'s body is exported as
`DecisionTrailEntries` and is the Decisions tab of `OrderInquiryLineHistoryDialog` (S0 as built;
the board and the worklist keep `DecisionTrailButton` and its dialog unchanged). Title "History -
<item> (<SO> L<n>)", `TabsList variant="line"`: Rows | Decisions | Reserve. Rows is a small `DataGrid`
(fixed layout, explicit sizes, truncate + title) inside its own horizontal scroller: When, Qty,
What, Document, Why. The live rows on top as "Now"; retired rows follow newest first. What is a
`Badge` pill: Now / Used / Superseded / Re-raised / Cancelled / Cancel balance / Line cancelled.
Re-raised has no note of its own: the carry site stamps the old row "Superseded by revision N",
the same as a plain supersede (L9), so S0 reads a superseded row as Re-raised when a later row of
the same line asks for the same qty again, and as Superseded otherwise. Why is the row's note; for a Now row with `previous_qty` it reads "Was <previous_qty>" before
the note (the one place the Was / now story lives, G1). Empty: "No earlier rows for this line."
Reserve tab only when the line has reserve history (today's `ReserveLineHistoryDialog` body
moves in, its icon goes).

S0 source for Rows: the live and used rows already loaded, plus the inquiry's cancelled rows
fetched once on first open with today's worklist filter (`inquiry_id` + `state=cancelled`,
`order_inquiry_worklist_service.py` 1231-1238), so S0 needs no mocked history. S1's
`include_history` folds that into the one Lines fetch.

The icon renders on every line row (the #1244 gate "has `core_line_id`" moves to "always"); the
Decisions tab reads "No decisions recorded for this line." when the line has no core line.

Motion: the dialog uses the standard lightbox surface spring; nothing else animates. No motion on
the fold, the row, the tabs switch (tens a day: none), or the History icon.

### Backend seam - presentation plus two read fixes, no migration

- The Lines tab fetch (`orderInquiryService.ts`, worklist endpoint with `inquiry_id`) gains
  `include_history=true`, which returns cancelled rows too (today they need `state=cancelled`).
  The FE partitions.
- `OrderInquiryWorklistRow` gains `so_line_qty` (SO line Qty as the SO grid shows it) and
  `so_line_no`; both declared on the schema and asserted by name (response_model drops undeclared
  fields).
- Header counts (`order_inquiry_header_service.py`), Owner ruling 26 Sep (G10): exactly the
  Lines tab's numbers. `lines_total` = the number of line rows the Lines tab renders (distinct
  sales order line over every non-cancelled row, used and cancelled-line included; a row with no
  line counts as one), `qty_total` = the Lines tab's Requested footer (sum of live buy rows'
  `qty`, used and cancelled-line rows excluded), `lines_to_confirm` = distinct lines with a live
  or used row in `awaiting` / `changed`. Fix round 2 (review S1): the line key is the row's
  mirror line `so_line_id`, else the row, so a line AutoCount has not reconciled yet is one
  line; the two line joins stay only for the cancelled-line test in `qty_total`.
- Confirm (G6): confirming a line's live rows also acknowledges that line's `redirected_to_pool`
  rows in `changed` on the same header, in the same transaction.
- No `superseded_by` column (G9). No alembic revision.

## Slices

| Slice | Phase | What | Blocks |
|---|---|---|---|
| S0 | 1 (FE mock) | Lines tab folds by sales order line from today's payload; No. / SO Qty / Requested / Taken / Remaining columns (SO Qty mocked); selection per line; one History icon + tabbed dialog (Rows from loaded rows plus the inquiry's cancelled rows); cancelled line grey. Owner hands-on on :3000 | S1 |
| S1 | 2 (BE, tester first) | `include_history`, `so_line_qty` / `so_line_no`, header counts (G10), Confirm sweeps used rows | S2 |
| S2 | 2 (FE wire) | swap the SO Qty mock for `so_line_qty`; one fetch with `include_history`; header list reads the new counts | S4 |
| ~~S3~~ | - | Dropped, owner ruling 26 Sep (G8): the worklist is being discontinued; no worklist change | - |
| S4 | 3 | reviewer + browser pass at 1280 and 375 (sidebar navigation from `/`), DoD gate, one PR | - |

## Conflicts with #1220 and #1244 (both merged on main, 26 Sep)

- `OrderInquiryDetail.tsx`: #1220 rewrote selection and Link selected around `activeLines`
  (main :202-250). S0 maps the line selection back to row ids at that seam, so every downstream
  mutation (Confirm, Unconfirm, Link selected, Unlink, Auto link) is unchanged.
- `orderInquiryHeaderLinesColumns.tsx`: #1220 added Suggested; #1244 put `DecisionTrailButton`
  in the State cell next to the reserve History icon (inside `ReserveActionsCell`). G3 merges
  both into one History icon; the reserve History icon goes and `ReserveLineHistoryDialog`'s body
  becomes the Reserve tab.
- `OrderInquiryLinesTab.tsx`: #1244's `initialState.columnVisibility` (`DEFAULT_HIDDEN_COLUMNS`)
  stays beside the fold.
- `DecisionTrailDialog.tsx` / `DecisionTrailButton.tsx` (#1244): extended with tabs, not forked.
  The board and the worklist keep calling the button as today (no tabs there).
- `schemas/project_order_inquiry.py` `OrderInquiryWorklistRow` and the worklist serializer: S1
  adds `so_line_qty` / `so_line_no` beside #1220's `suggested_links` and #1244's
  `raise_event_*`.
- `decision_trail_service._raise_entries` (#1244) matches rows to raise events by `created_at`; a
  replacement row reads as a fresh raise there. The Rows tab explains it; no change to #1244's
  service.
- Alembic: none from this lane.
- Standing rulings this plan changes (owner ruling 26 Sep, G6): C2
  (`PLAN-oi-cancelled-line-used-confirm.md`) and the 17 Sep "greyed with ONE one-word `used` mark
  on the Qty cell" ruling (`PLAN-oi-replan-received-links.md`) move from the main view into
  History on the detail; neither loses data. The worklist keeps them (G8).
- Grid census: the History dialog's Rows grid is registered in the SCROLLER census
  (`sorento_crm_frontend/components/ui/data-grid-scroller.inventory.test.ts`, `scrollerMaxHeight:
  false` inside its DialogBody). The NESTING census (`data-grid.nested.inventory.test.ts`) does not
  change: the dialog is a sibling of the Lines grid, not rendered inside it.

## Open

- O1: amendment-header rows (L16) for the same SO line live on another inquiry. Should the History
  Rows tab list them too (by `so_line_id` across headers)? Default: no, this inquiry only.
  Owner ruling 26 Sep: accepted, no.
- O2: a line whose rows are all retired (fully served by stock after a redirect) renders nothing
  on the detail. Alternative: one grey row "Nothing to buy" with History. Default in S0: render
  the grey row, so the SO line count still tallies; confirm with the owner on the mock.
  Owner ruling 26 Sep: accepted, one grey "Nothing to buy" row.
- O3: exports (D9) and the PO / SPO lightbox (D8) stay row-level. Named as follow-ups if the owner
  hits them.

## Out of scope

Any change to how rows are written (redirect, settle, netting, supersede); the board; reorder
planning; the handover email; the per-project order inquiry list (D6, legacy); `superseded_by`.
