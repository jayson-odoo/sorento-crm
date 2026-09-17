# UAC - Undo last confirm on the fulfilment planning board

Plan: `PLAN-board-undo-last-confirm.md`. Status: PLANNED, 17 Sep 2026, owner aligned on the Lavish page. Backlog row BL-063.

## Journey

**Actor:** CS planner on the fulfilment planning board. Purchasing is told, never asked.

**Where they arrive from:** the planner opened Supply Chain, Project Demand, Fulfilment
Planning for SO314595, decided five lines, pressed Confirm. Revision 1 is active; five OI
rows were raised and the handover email went to purchasing. Thirty seconds later the planner
sees the date on line 3 was wrong.

**What the system already knows:** which revision is newest on the order, who confirmed it and
when, whether purchasing has touched any of its rows since (a manual link, a row marked
actioned), and, from this lane on, exactly what that Confirm changed: the journal every
Confirm writes as it runs.

**Steps and the single decision each:**

1. Planner opens the gear menu on the board. Below "Undo all" (drafts) there is one entry per
   order on the board whose newest revision can be undone: `Undo SO314595 confirm (rev 1)`.
   An order purchasing has already acted on shows the entry disabled with the reason in its
   tooltip. An order with nothing to undo has no entry. Decision: pick the order.
2. The Confirm button slot turns into the countdown `Undoing SO314595 in 5s` with Cancel
   (System Settings reversible window). Escape does nothing. Decision: let it lapse, or Cancel.
3. The window lapses. The server replays the journal backwards: the revision row goes,
   the previous revision (or "nothing decided" for revision 1) is active again, every OI row,
   link, claim, note, stock transfer, decision draft and planning-change batch row is as it
   was the moment before Confirm. The board reloads and shows the five lines undecided, the
   planner's drafts back in the panel. No decision asked.
4. Planner fixes line 3 and presses Confirm again. Revision 1 is minted again, with a fresh
   journal, undoable again.

**What they hold at the end:** the board as it was before the wrong Confirm, the drafts they
had typed, and one new revision once they re-confirm. The undone revision leaves an audit row
and nothing else.

**What every other stakeholder is told automatically:** purchasing gets one email per undo,
"Order inquiry undone", listing the SO and every row that went back or vanished, through the
same automation method as the handover email (#962). If purchasing had already linked a PO
line by hand or marked a row actioned, the undo is refused before anything moves; the planner
sees the reason on the disabled menu entry.

## Rulings (owner, 17 Sep 2026)

- R1 refusal: only a link purchasing (or AutoCount) put on a row after the confirm, or a row
  marked actioned after the confirm, blocks undo. A sent email, an acknowledgement or a note
  edit does not. "After the confirm" is decided from the confirm's own journal, on every order
  the journal touched.
- R2 exact restore: the data is what it was before the Confirm click, drafts included.
- R3 depth: one revision back, once. The reinstated revision is not undoable.
- R4 batch fork: undo returns the planning-change batch to pending. No book rewind (ruled 17
  Sep on the Lavish page): the book stays where the AutoCount upload put it.
- R5 email: an automation, same method as #962.
- R6 placement: gear dropdown, same permission as Confirm, deferred-action countdown, hidden
  when nothing is undoable.

## Phase 1 (frontend, mocked)

- AC-UC-01 [FE] Given the board holds SO314595 with an undoable revision 1, when the planner
  opens the gear menu, then it lists `Undo SO314595 confirm (rev 1)` below "Undo all".
- AC-UC-02 [FE] Given the board holds three orders of which two are undoable, when the gear
  opens, then exactly two undo entries appear, one per undoable order, ordered as the board.
- AC-UC-03 [FE] Given an order whose undo is refused (`refusal = "linked"` or
  `"actioned"`), when the gear opens, then its entry is present, disabled, and the reason
  "Purchasing linked a PO line" or "Purchasing marked a row actioned" is visible as muted
  text inside the item (a `title` on a disabled item never renders).
- AC-UC-04 [FE] Given no order on the board is undoable, when the gear opens, then no undo
  entry and no separator for it render.
- AC-UC-05 [FE] Given the planner selects an undo entry, when the pending action is created,
  then the Confirm button slot shows the countdown `Undoing SO314595 in Ns` with Cancel,
  driven by the server `commit_at`, and Escape does not cancel it.
- AC-UC-06 [FE] Given a countdown is running, when the planner presses Cancel before it
  lapses, then the Confirm button returns and the board is unchanged.
- AC-UC-07 [FE] Given the countdown lapsed and the server committed, when the board refetches,
  then the affected lines render undecided and the gear entry for that order is gone.
- AC-UC-08 [FE] Given the board is opened at `?batch=<id>` and the batch was applied by the
  revision being undone, when the undo commits, then the batch shows pending again on reload.
- AC-UC-09a [T] Vitest over a mocked board payload covers AC-UC-02, AC-UC-03 and AC-UC-04.
- AC-UC-09 [UX] At 375px and 1280px the countdown fits the action bar without clipping; the
  gear entry text truncates with `title`. No new motion: the countdown reuses
  `DeferredCountdown`; the menu uses the existing dropdown preset.

## Phase 2 (backend, tester first)

Journal at confirm:

- AC-UC-10 [BE] Given a plain Confirm of two lines, when it commits, then the new
  `so_supply_decisions` row carries `undo_journal` JSON naming every row the transaction
  inserted (table, pk), updated (table, pk, old values of changed columns) and deleted (table,
  pk, full row), including `so_line_allocations`, `order_inquiry_rows`, `order_inquiry_links`,
  `scm.order_link_claim`, `so_supply_decision_drafts`, `stock_transfers` and the superseded
  decision's `state` / `superseded_at` / `superseded_reason`.
- AC-UC-11 [BE] Given a Confirm carrying `batch_id`, when it commits, then the journal also
  holds the `planning_change_rows.applied_state` / `result_json` and
  `planning_change_batches.applied_at` / `applied_by` / `result_json` old values.
- AC-UC-12 [BE] Given a Confirm that borrows from a donor order (re-issue without line), when
  it commits, then the donor's superseded and re-issued decision rows are in the same journal.
- AC-UC-13 [BE] Given `confirm-all` over three orders where the second refuses, when it
  returns, then the first and third decisions each carry their own journal and the second
  wrote nothing.
- AC-UC-14 [BE] Given a purchasing rejection re-issues a revision through `uncover_lines`,
  when it commits, then that revision has NO journal (only the two board confirm routes
  journal).
- AC-UC-15 [BE] Given a decision row, when the board payload is built, then each order carries
  `undo: {decision_id, revision_no, confirmed_at, confirmed_by_name, refusal}` (refusal null, `linked` or `actioned`) when its newest active
  decision has a journal, else `undo: null`.

Undo service:

- AC-UC-16 [BE] Given revision 2 with a journal supersedes revision 1, when undo commits, then
  revision 2's row is gone, revision 1 is `active` with `superseded_at` and
  `superseded_reason` NULL, and every allocation, OI row, link, claim, note, draft and stock
  transfer equals its pre-confirm value column for column (the tester snapshots the tables
  before Confirm and diffs after undo; the only allowed differences are `updated_at` and, on the reinstated decision, `undo_journal`, which R3 clears).
- AC-UC-17 [BE] Given revision 1 (nothing before it), when undo commits, then the order has no
  active decision, no OI rows raised by it, the drafts the planner had are back, and the
  board reports the lines undecided.
- AC-UC-18 [BE] Given the confirm deleted a link and freed its claim, when undo commits, then
  the link and the claim exist again with their original ids, `linked_at`, `auto`, `linked_by`.
  A link the same confirm drafted and then removed does not come back.
- AC-UC-19 [BE] Given a settled-in-place row whose `note` was appended and whose `previous_qty`
  was overwritten, when undo commits, then `note`, `previous_qty`, `previous_delivery_date`,
  `ack_state`, `acknowledged_by`, `acknowledged_at`, `changed_at`, `supply_decision_id` all
  equal their pre-confirm values.
- AC-UC-20 [BE] Given a redirected row (`redirected_to_pool` set by the confirm) whose open
  links were removed, when undo commits, then the flag is back to its old value and the
  removed links exist again.
- AC-UC-21 [BE] Given the undone confirm carried a `batch_id`, when undo commits, then the
  batch's rows are `pending` again, `applied_at` / `applied_by` / `result_json` are back to
  their old values, and the SO book lines are NOT changed (R4).
- AC-UC-22 [BE] Given revision 2 was undone and revision 1 is active again, when the board is
  built, then `undo` is null for the order (revision 1's journal was cleared: R3). Given two
  journaled confirms, then only the newest decision holds a journal.
- AC-UC-23 [BE] Given a link this confirm did not write (auto or manual) with `linked_at`
  later than `confirmed_at` exists on a row of any order the journal touched, when undo is
  requested, then it is refused with 409 and `refusal = "linked"`, and nothing changed.
- AC-UC-24 [BE] Given a row of a touched order became `actioned` after this confirm ran, when
  undo is requested, then 409 `refusal = "actioned"`, nothing changed. A row already actioned
  before the confirm, re-stamped by the confirm's own cascade or untouched, does not refuse.
- AC-UC-25 [BE] Given the confirm's own step-3 borrow placement wrote a link (a REAL
  placement, its id in the journal's insert set), when undo is requested, then it is NOT
  refused.
- AC-UC-26 [BE] Given the newest revision has no journal (pre-lane revision, or minted by
  `uncover_lines`), when undo is requested, then 409 `refusal = "no_journal"`.
- AC-UC-27 [BE] Given the pending-actions engine, when `project_sales_order.undo_confirm` is
  created for `entity_type = project_sales_order`, then it uses the reversible window, requires
  `projects.projects.edit`, and commits the undo when the window lapses even with no client
  polling (scheduler sweep). Given the refusal predicate already rejects the order, when the
  action is created, then 409 with the refusal code and no pending row; a refusal that arises
  during the countdown still resolves `ineligible` at commit.
- AC-UC-28 [BE] Given a second Confirm was written after the pending undo was created, when the
  window lapses, then the undo targets the revision named at creation and refuses with
  `refusal = "superseded"` if it is no longer the newest.
- AC-UC-29 [BE] Given the undo commits, then one `audit_logs` row records the DELETE of the
  undone decision with its old values (existing `SOSupplyDecision` audit tracking), and no
  `audit_logs` row anywhere carries `undo_journal`.
- AC-UC-30 [BE] Given a user with `projects.projects.view` only, when they create the pending
  action, then 403 and no row. Given a user with `projects.projects.edit` who may not edit the
  order's project (not owner, not approved collaborator), when the action executes, then the
  same refusal Confirm gives and nothing changed. Given no `decision_id` in the payload, then
  400.
- AC-UC-31 [BE] Given a user of another company, when they request undo on this order, then
  404 (company scope), nothing changed.

Email:

- AC-UC-32 [BE] Given an undo commits, then `AutomationService.dispatch_event` is called once
  with trigger `order_inquiry_undone`, listing only rows of the undone order (never a donor's),, context `{undo: {so_number, customer, project,
  revision_no, lines: [{item_code, qty, delivery_date, outcome}], link}, actor, today}`, after
  the root transaction commits, on a fresh session.
- AC-UC-33 [BE] Given the undo is refused or rolls back, then no dispatch happens.
- AC-UC-34 [BE] Given a fresh database, when the migration runs, then an enabled automation
  "Order inquiry undone" with trigger `order_inquiry_undone`, `recipient_config` matching
  the handover row (purchasing roles, `include_actor`, `one_email`), and template
  `order_inquiry_undone_default` exist; re-running the migration skips, never updates.
- AC-UC-35 [BE] Given the trigger catalog, then `order_inquiry_undone` is listed with an empty
  config schema and a pull evaluator returning `[]`.

## Phase 3

- AC-UC-40 [E2E] On `sorento_ai_automation_0915_1900`: confirm SO314593 from the board
  (fresh revision with a journal), undo it from the gear, let the countdown lapse; the OI
  worklist shows OI-000477 rows exactly as before the confirm, the board shows the lines
  undecided, the audit row exists, one dispatch captured. Evidence: screenshots before,
  during countdown, after; SQL diff of the seven tables.
- AC-UC-41 [E2E] Same order: confirm, have a purchasing user link a PO line by hand, open the
  gear; the entry is disabled with the reason; the pending-action POST answers 409.
- AC-UC-42 [T] Kill tests: comment out the refusal check (AC-UC-23 goes red), comment out the
  journal clear on the reinstated decision (AC-UC-22 goes red), comment out the deleted-row
  re-insert (AC-UC-18 goes red).
