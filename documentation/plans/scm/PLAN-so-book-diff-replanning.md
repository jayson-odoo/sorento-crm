# PLAN - what a change to the AutoCount sales-order book does to the plan

**Status:** DRAFT for captain review, 19 August 2026. Journey and UAC agreed in shape by the
captain on the evening of 18 August ("I agree with your proposed shape overall"); this file is
the contract. Phase 1 (frontend mock) may start once the captain has read section 0 and 1.

**Slug:** so-book-diff-replanning. **Sits on:** `PLAN-fulfilment-planning-from-autocount-so.md`
(the board, adoption, the ladder, Order Inquiries) and `PLAN-scm-front-planning.md` (the ladder's
rules: reserve, hot-selling, discontinued, borrow, buy).

## The captain's ask, verbatim (18 August 2026)

> "how do we handle revision, in which for this delivery schedule ... they want to delay the
> floor trap delivery, so by right we should be able to upload the revision with respect to this
> delivery schedule, and system suggest the change to delivery schedule, then user confirm, then
> we can revise the SO based on the revised delivery schedule, in which we also suggest the
> revision, then the user can accept / reject the revision, take it to autocount, change, then
> reupload the sales order back to our system, then we can trigger the replanning and revision
> to the order inquiries, this is a chain reaction, have we covered this?"

> "we don't need to join from R2 to an autocount SO, we just need to suggest the change to our
> project SO, then the user will revise in autocount, in which they are allowed to reupload ...
> the objective I want to achieve is based on the diff of autocount SO, what's the change to the
> planning and order enquiries, like if there is delay, do we need to release back to BRW? this
> is based on project / dealer hot selling or not, whether the product is discontinued or not,
> whether the delay is big or small, then when the project is advanced, it should enter the
> planning also to go through the cycle of fulfilment planning la, like whether got stock,
> whether can cut queue, whether brw got stock, whether incoming got stock, whether can borrow,
> then last resort is buy, similar logic that we established"

## What already exists (measured 18 August, scout report)

The chain has two halves. The first half - revised schedule in, suggested SO change out - EXISTS
for a CRM-authored project SO: `DeliveryScheduleVersion` (R1/R2 are two documents of one
commitment), upload-as-revision, confirm, and `project_so_delta_service` producing the client's
own verbs (ORDER, RESERVE & ORDER, ADVANCE, DELAY, CHANGE SO NO, CANCEL BALANCE) with the golden
R1->R2 test (`test_the_r1_to_r2_revision_delays_every_phase_and_touches_no_quantity`). Its gaps
are small and listed in section 9.

The second half - the re-uploaded AutoCount book changes a planned line, and the plan REACTS -
does not exist. `outstanding_import_service.apply()` diffs the book correctly (ADDED / UPDATED /
CLOSED, never deletes) and by design raises no project signal. The only reaction today is lazy:
`challenge_if_drifted()` flips a confirmed decision to `challenged` when somebody next opens that
order's sheet, and nobody is told. Order Inquiry rows are not touched. That second half is what
this plan builds. The first half's small gaps ride along as section 9.

## 0. Journey (design before schema)

**Actor:** the project planner (office / CS), the same person who plans on the board. Purchasing
is the second stakeholder and is only told, never asked.

**Where they arrive from:** the SO-book upload confirmation screen (SCM -> Sales Orders ->
Upload), the moment the re-uploaded book has been applied. That is where the change is born, so
that is where the reaction is offered. A sidebar entry (Project Sales -> Planning changes) lists
the same thing later, for the planner who was not the uploader.

**What the system already knows, so it never asks:** which of the changed lines belong to an
order that is planned (adopted or authored-and-adopted), which of those carry an active decision
and what it holds (reserve at which location, borrow from whom, buy how much), whether the product
is dealer hot-selling or discontinued, whether the delay is inside or outside the reserve window,
what the ladder would propose for the line at its new date, and which Order Inquiry rows the line
already raised.

**Step 1 - "The book moved 14 planned lines."** After apply, the confirmation screen shows one
card per planned order that changed, and inside it one row per changed line with: what changed
(`Required 04 Feb 2027 -> 18 Feb 2027 (+14 days)`, `Qty 72 -> 66`, `Closed`, `New line`), what
the line's decision holds today (`Reserve 66 at BRW-BB · Buy 6`, or `Not decided`), and the
system's **suggested reaction** as a verb the planner already knows from the board:
`Keep`, `Release`, `Replan`, `Reduce`, `Retire`. The one decision per row: accept the suggestion,
or not.

**Step 2 - the planner accepts per row.** Accept-all is the default and the common case; a row
can be switched to `Keep as is` (do nothing to the plan) or `Open on the board` (the cell for that
line, where Amend does the rest). Nothing is written until Apply.

**Step 3 - Apply.** One press. For every accepted row the plan is revised: holds released or
kept, decisions re-issued as a new revision covering the union, lines that need a fresh look
re-enter the board undecided, Order Inquiry rows revised with the previous value carried (DELAY,
ADVANCE, CANCEL BALANCE, retire), purchasing notified once per order.

**What they hold at the end:** a plan that agrees with the book, a board whose cells for the
moved lines show either the kept decision or a fresh proposal, and an Order Inquiries worklist
where purchasing sees `DELAY: was 04 Feb, now 18 Feb` against the rows they were about to buy.
The change list stays readable afterwards (Project Sales -> Planning changes) with who applied
what and when.

**The rules the suggestion follows** (the captain named the inputs; the thresholds reuse existing
constants, no new knob):

| Change | Facts | Suggested reaction | Why |
|---|---|---|---|
| Delay, new date within `RESERVE_WINDOW_DAYS` (60) of today, product not hot-selling | decision holds a reserve | **Keep** (snapshot refreshed, OI DELAY row) | A short slip on stock already held; releasing and re-taking would only reshuffle the queue |
| Delay beyond the window, product not hot-selling, not discontinued | holds a reserve | **Release** the reserve back to its location; line stays decided for incoming/buy parts, reserve part becomes undecided; re-enters the board when its bucket nears | Stock sits idle for months while others queue behind it |
| Delay of any size, product **dealer hot-selling** | holds a reserve at BRW pool | **Release** | Retail needs BRW stock now; the ladder will not have proposed own-location stock for a hot-selling item anyway |
| Delay of any size, product **discontinued** | holds a reserve | **Keep**, whatever the delay | It cannot be bought again; releasing it is giving it away |
| Delay, decision holds only Buy | OI rows raised, not yet actioned | **Keep** the decision, OI row gets **DELAY** with the previous date | Purchasing decides whether to postpone the PO |
| Delay, Buy already actioned (PO placed) | | **Keep**, OI row DELAY, note "PO placed" | Nothing to undo in the plan |
| Advance (earlier date) | any | **Replan**: decision challenged, the line runs the ladder again at the new date NOW (rank rises, queue position changes); the fresh proposal shows in the row and on the board; planner confirms there | The captain's "it should enter the planning again and go through the cycle" |
| Qty up | any | **Replan** the delta only: existing components kept, the extra quantity runs the ladder | Same cycle, smaller |
| Qty down | holds reserve/buy | **Reduce**: reserve released for the drop, Buy reduced, OI row CANCEL BALANCE for the drop | |
| Line closed in the book | any | **Retire**: release everything, retire OI rows, decision revision drops the line | |
| New line on a planned order | | **Replan**: enters the board undecided (already what the board does for any open line) | |
| Line changed on an order that is NOT planned | | Not shown here at all | The board handles unplanned demand as it always did |

`Release` never happens silently: it is a suggestion the planner accepts. Every reaction that
touches purchasing rows carries the previous value (the DELAY that is actionable is the one that
says what it was).

## 1. User Acceptance Criteria

Every AC traces to a journey step. "Planned line" = a line of an order that has a planning record
(adopted mirror or authored-and-adopted), whether or not it has a decision.

**AC-R01 (step 1, born at upload).** Given a re-uploaded SO book whose apply changed the
required date, quantity or open state of at least one planned line, when apply completes, then a
`planning_change_batch` exists for that upload with one row per changed planned line, and the
upload confirmation screen shows the batch (`The book moved N planned lines on M orders`) with a
link to review it. An upload that changes no planned line creates no batch and shows nothing.

**AC-R02 (step 1, the row).** Each row states the line (SO no, line, product, customer, project
if any), the change (`kind` in `delayed | advanced | qty_up | qty_down | closed | added`, with
`from` and `to`), what the active decision holds today (components with locations), the facts
the rule used (`dealer_hot_selling`, `discontinued`, `days_moved`, `within_reserve_window`,
`buy_actioned`), and the suggested reaction (`keep | release | replan | reduce | retire`) with a
one-line why. Nothing is inferred by the reader; the row says which fact chose the verb.

**AC-R03 (step 1, no decision).** A changed planned line WITHOUT an active decision shows
`Not decided` and the reaction is always `replan` (it is simply on the board at its new
date/quantity); no hold or OI row is touched. Such rows are shown but need no acceptance.

**AC-R04 (step 2, per row).** Each row with a decision offers `Accept` (default on), `Keep as
is`, and `Open on the board` (deep link to the cell of that line, existing route). Switching a
row writes nothing.

**AC-R05 (step 3, apply is atomic per order).** Apply revises each affected order's decision as a
NEW revision covering the union of untouched covered lines and the accepted reactions (the same
rule the board's second confirm follows, PLAN 13.4). If one order's revision fails, that order is
left at its previous revision and named in the result; the others still apply. Applying twice is
a no-op (`already_applied`).

**AC-R06 (step 3, release).** An accepted `release` removes the reserve component(s) from the
line's frozen composition; the stock is free at that location again on the next read of the
board, the sheet and the stock detail; the line's remaining components (incoming, buy) stay
frozen; the line shows on the board as `Confirmed rev N · Buy 6 (reserve released 14 Feb)`; the
released quantity is visible in the batch afterwards.

**AC-R07 (step 3, replan).** An accepted `replan` challenges the line's decision (existing
`challenged` state) and the batch row shows the ladder's fresh proposal for the line at its new
facts (same fields as a board contribution: sources, trail); the line is undecided on the board
until confirmed there. Nothing is auto-confirmed.

**AC-R08 (step 3, Order Inquiries).** For every accepted reaction on a line with OI rows: delay ->
`DELAY` change row carrying the previous date; advance -> `ADVANCE`; qty down -> `CANCEL BALANCE`
for the drop; closed -> rows retired; release -> no OI change (a reserve is not a purchase). Rows
already `actioned` are never retired; they get the change row and a note.

**AC-R09 (step 3, told).** Purchasing is notified once per order with a batch link (in-app; the
existing `project_order_inquiry_raised` channel and its rule for adopted orders without a project,
whichever holds when this lands). The planner who applied is not notified.

**AC-R10 (later, the list).** Project Sales -> Planning changes lists batches newest first
(upload time, uploader, orders, lines, applied by / at, pending), and each batch reads exactly as
it did at step 1 plus what was applied. Retention: the batch is a record, never deleted.

**AC-R11 (safety).** A batch older than the order's latest revision (somebody re-planned on the
board in between) shows the row as `superseded on the board` and disables Accept for it.

**AC-R12 (rules pinned).** Each row of the table in section 0 has one backend test that seeds the
facts and asserts the verb and the why. Hot-selling uses the existing predicate (ABC A at an
active dealer warehouse); discontinued uses `products.is_discontinued`; the window is
`RESERVE_WINDOW_DAYS`.

## 2. Design, backwards from the journey

**Where the batch is born.** After `outstanding_import_service.apply()` flushes its diff, a
best-effort post-apply hook (the same shape as the reorder plan-exception batch it already emits,
AC-D2a: produced on confirmation, never fails the upload) hands the diff to
`planning_change_service.build_batch(diff, upload)`. That service keeps `outstanding_import_service`
ignorant of the project module, exactly as `project_so_ingest_service` does today: it is called
from the upload route after apply, not from inside apply.

**Filter to planned lines.** Join changed core line ids to `projects.sales_order_lines`
(mirror lines, `core_line_id`) whose order has a planning record. Unplanned demand is out.

**Facts per row.** `ProjectSupplyService.frozen_lines_of(active decision)` for what is held;
`_hot_selling` / `_discontinued` (existing) for the product; days moved from the diff; OI rows for
the line via `project_order_inquiry_service` (existing lookups); `buy_actioned` = any OI row of the
line in `actioned`.

**The suggestion.** A pure function `suggest(change, held, facts) -> (verb, why)` implementing
the section-0 table. No I/O; tested per row of the table (AC-R12).

**Fresh proposal for replan/qty_up.** Reuse the board's per-line composition: build a one-line
board request (`FulfilmentBoardService.build` for the order, take the contribution) so the row
and the board show the same proposal and trail. No second engine.

**Apply.** `planning_change_service.apply(batch, accepted_row_ids, actor)`:
- group by order; per order compose the union body from `frozen_lines_of` minus released
  reserve components minus reduced quantities minus retired lines; call the existing
  `ProjectSupplyService.confirm(order, body)` (all-or-nothing per order, AC-C01 as amended);
  `replan` rows are excluded from the body and challenged through `challenge_if_drifted`'s
  existing transition (a direct `challenge(decision, reason)` seam if none exists);
- OI revision through the existing `derive_for_amendment`-style verbs
  (`project_order_inquiry_service`), extended with a `derive_for_book_change(batch_rows)` that maps
  `delayed -> DELAY`, `advanced -> ADVANCE`, `qty_down -> CANCEL BALANCE`, `closed -> retire`;
- notify per order through `_notify_purchasing`.

**Data.** Two tables, both append-only records:
`projects.planning_change_batches (id, company_id, upload_id/source ref, created_at, created_by,
applied_at, applied_by, order_count, line_count)` and
`projects.planning_change_rows (id, batch_id, project_sales_order_id, project_line_id,
core_line_id, kind, from_json, to_json, held_json, facts_json, suggested, why, decision
(accept|keep|board|null), applied_state (pending|applied|failed|superseded), result_json)`.
One alembic revision chained on the current single head. `line_snapshots` untouched.

**What this does NOT do.** It does not write to AutoCount, does not auto-confirm a replan, does
not create decisions for lines that had none, does not touch unplanned demand, and does not
replace the lazy `challenge_if_drifted` (which stays as the safety net for edits that bypass the
upload).

## 3. API contract (Phase 1 mocks against this; Phase 2 must match)

- `GET /api/v1/project-sales/planning-changes` -> list of batches (DataGrid contract, sortable by
  created_at, filter `pending|applied`).
- `GET /api/v1/project-sales/planning-changes/{batch_id}` ->
  `{id, created_at, created_by_name, source: {upload_id, file_name}, applied_at, applied_by_name,
  orders: [{project_sales_order_id, so_number, customer_name, project_label, revision_no,
  rows: [{id, line_no, item_code, product_name, kind, from: {required_date, qty, status},
  to: {...}, days_moved, held: {reserve: [{location, warehouse_id, qty}], borrow: [...], buy_qty,
  timely_spo_qty, revision_no}, facts: {dealer_hot_selling, discontinued, within_reserve_window,
  buy_actioned}, suggested: 'keep|release|replan|reduce|retire', why, proposal: BoardContribution
  | null (replan/qty_up only), inquiry_rows: [{id, verb, qty, state}], decision: 'accept|keep|
  board|null', applied_state, board_link: '/project-sales/fulfilment-planning?orders=SO..&cell=..'}]}]}`
- `PUT /api/v1/project-sales/planning-changes/{batch_id}/rows/{row_id}` body `{decision}`.
- `POST /api/v1/project-sales/planning-changes/{batch_id}/apply` -> `{applied_orders: [...],
  failed_orders: [{so_number, reason}], already_applied: bool}`.
- The upload confirmation response gains `planning_change_batch: {id, order_count, line_count} |
  null`.

## 4. Frontend shape

- Upload confirmation screen (existing, `scm/sales-orders` upload flow): a card `The book moved
  N planned lines on M orders` with `Review` -> the batch page.
- Batch page `project-sales/planning-changes/[batchId]`: header (source upload, when, by whom,
  Apply button with count), one section per order (`SO403765 · BATHE CODE · rev 2`), a
  `PanelDataGrid` of rows: `Line | Product | Change | Held today | Facts | Suggested | Why |
  Decision`. Facts as small chips (`hot-selling`, `discontinued`, `+14 d`, `PO placed`).
  Suggested as the verb pill. Decision = segmented control Accept / Keep as is / Open on the
  board. Replan rows show the fresh proposal in the same source-strip + trail-popover components
  the board uses (reuse, do not copy). Every section renders, including an order whose rows are
  all `Not decided`.
- List page `project-sales/planning-changes` (sidebar under Project Sales): DataGrid of batches.
- Board: a covered row whose reserve was released reads `Confirmed rev N · Buy 6 · reserve
  released 19 Aug` (pill), Amend still available.
- Order Inquiries worklist: DELAY / ADVANCE / CANCEL BALANCE rows render as they already do for
  amendments, with the previous value.

## 5. Phasing

- **Phase 1 (mock):** batch page + list page + upload card against a fixture batch that has one
  row per rule of the section-0 table; every state (pending, applied, failed order, superseded
  row, no-decision row). Screenshots. Contract above.
- **Phase 2:** migration, `planning_change_service` (build, suggest, apply), post-apply hook,
  routes, OI derive, notify; pytest per AC; FE off mocks; evidence run: re-upload a book that
  delays SO403765's floor-trap lines by 14 days and by 90 days, advance one line, close one -
  review, apply, check board + Order Inquiries.
- **Phase 3:** review.

## 6. Decisions and open questions

- Thresholds: `RESERVE_WINDOW_DAYS` is the delay size boundary. Open: the captain may want a
  different number for release than for reserve; if so, one constant, named, next to the other,
  no settings knob unless asked.
- Hot-selling: dealer hot-selling only exists (ABC A at a dealer warehouse). "Project hot-selling"
  is not a concept in the system today; if the captain means one, define the predicate first
  (open).
- Order-back for released stock: none. A release returns stock to its location; whoever queues
  for it takes it through the ladder.
- Advance replan is proposed, never auto-confirmed (captain: "user confirm").
- Whether an authored (non-adopted) project SO's lines are also "planned lines" here: yes if the
  order has a planning record; the batch does not care how the record was born.
- **Release (Phase 2, 19 August 2026):** a released line returns WHOLE to the board rather than
  keeping its buy parts frozen - `_check_line` permits no partial cover; a partial-cover seam is
  a follow-up.

## 7. Risks

| Risk | Mitigation |
|---|---|
| A big book upload changes hundreds of planned lines | Batch build is one pass over the diff, facts batched per product/order; the page groups by order and paginates rows; Apply is per order |
| Apply half-succeeds | Per-order atomicity, failed orders named, re-apply skips applied orders |
| The board re-plans a line between review and apply | AC-R11 supersession by revision number |
| Two uploads before anyone reviews | Each upload gets its own batch; a row for a line already pending in an older batch marks that older row `superseded by a newer upload` |

## 8. Facts to measure before Phase 2

- How many planned lines the live book re-upload changes on the e2e stack (expected small; the
  captain's floor-trap case is a handful of lines on one order).
- Whether `challenge_if_drifted` already offers a direct challenge seam or only the drift path.
- Whether the upload confirmation screen has a natural slot for the card (it already shows the
  reorder exception batch count, so yes in principle).

## 9. The first half's small gaps (revised schedule -> suggested SO change), riding along

Scouted 18 August; none is a blocker for the second half but the captain's journey wants them:

1. The schedule review renders only the new dates; `promoted_delivery_date` (was) is served and
   unrendered, and cell quantities are not compared with the prior version. Add a was->now diff
   view (dates and quantities) to the schedule version page.
2. Confirming a schedule version notifies nobody that the linked SO is now stale. On confirm,
   raise the amendment preview for the linked SO and notify the planner.
3. Amendment review is all-or-nothing. Add per-row accept/reject on `AmendmentDeltaTable`
   (accepted rows form the amendment; rejected rows are recorded as declined with a reason).
4. The output of an accepted amendment is what the user keys into AutoCount: add an
   "AutoCount change list" view/export of the accepted rows (SO no, line, product, old -> new
   qty/date, verb) so the AutoCount edit is a copy, not a re-derivation. Then the book re-upload
   closes the loop through the second half of this plan.
5. `AUTHORED_LIVE_STATUSES` is required at every OUT site (PLAN-fulfilment 4) but
   `project_so_delta_service.py:549` still uses the inline literal pair - use the constant.
6. The extractor read `7/1/2027` as `2027-07-01` on one page of R2 and `2027-01-07` on the
   others (seen live 19 August). Day-first is the customer's convention; pin it in the extraction
   prompt/normaliser and add the R2 fixture case.

7. **The revision that is prose and colour, not a new column** (seen live 19 August, R2 of
   Tuju Residences, version e36327d7). Page 7 keeps R1's phase columns and carries the change
   as a margin note - `ONLY FOR FLOOR TRAP TO BE DELIVER IN 2026, START FROM 23/7/2026` - with
   the affected cells filled rose (`#DB9694` / `#E5B8B8` over SRT382-6's twelve TOWER cells,
   135 then 72 x 11; the common-area cells untinted). The extractor read the columns and
   nothing else, so R2 extracted identical to R1 and the review had no diff to show. The
   captain: "all the red coloured cell is moved starting from 23/7, with the same cadence ...
   we need to be smart enough to identify the affected phases and the cadence."
   Build, in order: (a) the text-layer parser tags each cell inside a coloured fill (grey
   excluded) with its `highlight` colour, and every page's free-text remarks are captured
   verbatim as `notes[]` (the LLM path returns the same two fields; geometry wins when both
   exist); (b) a post-extraction proposal per product with highlighted cells whose page note
   names a date: first highlighted phase -> the note's date, each later highlighted phase ->
   previous + the ORIGINAL gap between those phases (the cadence is the document's own, never
   a constant), quantities untouched, stored as `revision_proposals` on the version
   (`proposed | accepted | rejected`, who/when); (c) `delivery_schedule_cells.delivery_date_override`
   (nullable) written when a proposal is accepted, and `project_so_delta_service` reading the
   override for that product-phase so the amendment proposes ADVANCE / DELAY per line; (d) the
   review shows highlighted cells tinted, the notes as a callout beside the rows they sit on,
   and one proposal card per product ("Re-date 12 phases from 23/07/2026, fortnightly:
   07/01/2027 -> 23/07/2026, 21/01/2027 -> 06/08/2026, ...") with Accept / Reject; accepted
   dates render as was -> now (item 1). Nothing is inferred beyond note date + highlight +
   original cadence; a note without a date, or highlights without a note, show as-is with no
   proposal.
