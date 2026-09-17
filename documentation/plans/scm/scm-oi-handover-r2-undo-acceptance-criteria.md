# UAC: order inquiry handover email r2, depth-N undo, reconstructed undo

Status: grilled 18 Sep 2026; rulings Q1 admin only, Q2 changed guard on, Q3 one settled line, Q4 confirm email includes still-raised amendment rows; next: tickets
Plan: `documentation/plans/scm/PLAN-scm-oi-handover-r2-undo.md`
Supersedes ruling R3 of the archived `PLAN-scm-oi-handover-email.md` (struck-through cell) and
ruling 3 of `PLAN-board-undo-last-confirm.md` (one step, once).

## Journey

**Actor 1: the CS planner (Eling), on the fulfilment planning board.** She arrives from
Project Sales > Fulfilment planning with one or two sales orders filtered in, decides every
line, presses Confirm. The system writes the revision, raises the purchasing rows, and sends
purchasing ONE email. Nothing else to do. She holds a Confirmed board and the knowledge that
purchasing has one page that matches it.

**Actor 2: purchasing (Joey), reading the email.** One table per email. Each line says the
item, the quantity it is now, the delivery date it is now, and, when either moved, what it was
in a column of its own, in the words the manual mail always used (`QTY` old, `QTY CHANGE TO`
new). No strikethrough to decode, no cancel-then-order pair to net out. Every date reads
`dd/mm/yyyy`. She does not have to open the CRM to understand it.

**Actor 3: the planner again, after a Confirm went wrong.** A wifi outage swallowed the
Confirm response, the board re-saved the lines as drafts, she confirmed again, and purchasing
got a second email full of cancel + re-order pairs. She opens the board's gear menu and finds
`Undo SO314594 confirm (rev 2)`. She presses it, waits out the countdown, and rev 1 is back.
The gear now offers `Undo SO314594 confirm (rev 1)`. She presses that too. The board is
undecided again, her saved drafts are back in the panels where the journal had them. She
re-enters the two rejects the journal never held, confirms once, and purchasing gets one
email. Purchasing is told about each undo as it happens.

**Actor 4: the admin (Jayson), on an order confirmed before undo existed.** Same gear menu,
but the entry reads `Undo SO314594 confirm (rev 2), reconstructed` with a second line saying
what will not come back (saved drafts, row notes). He presses it twice, re-enters the two
rejects, confirms once. One email, the right one.

Decisions the actor makes: which order to undo (one click), whether to proceed on a
reconstructed undo (the countdown is the confirmation). Everything else is derived.

## Phase 1 (frontend, mocked)

- **AC-R2-F01 [FE]** Given the board response carries `undo.mode = "journal"`, when the gear
  menu opens, then the entry reads `Undo <SO> confirm (rev N)` exactly as today, no second line.
- **AC-R2-F02 [FE]** Given `undo.mode = "reconstructed"`, when the gear menu opens, then the
  entry reads `Undo <SO> confirm (rev N), reconstructed` and a second line
  `Saved drafts and row notes are not restored` is visible text in the item, not a title.
- **AC-R2-F03 [FE]** Given `undo.refusal = "changed"`, when the gear menu opens, then the entry
  is disabled and its second line reads `A row changed since this confirm`.
- **AC-R2-F04 [FE]** Given a reconstructed entry is pressed, when the countdown runs, then the
  Confirm slot shows the same `DeferredActionButton` countdown as a journal undo (`Undoing
  <SO>`) and Escape does not cancel it. No new component, no motion beyond the existing
  countdown fill.
- **AC-R2-F05 [FE]** Given an undo commits and the board refetches, when the reinstated revision
  is itself undoable, then the gear menu shows `Undo <SO> confirm (rev N-1)` without a page
  reload.
- **AC-R2-F06 [UX]** Usable at 375px and 1280px: the two-line gear entry truncates with a
  `title`, never wraps the menu wider than the viewport.

## Phase 2 (backend, test-first)

### S1 Email layout

- **AC-R2-01 [BE]** Given a handover email renders, when the line table prints, then its columns
  are exactly `SO DATE | S/O NO | ITEM CODE | QTY | QTY CHANGE TO | DELIVERY DATE | DELIVERY DATE
  CHANGE TO | REMARK`, in that order, in both `body_html` and `body_text`. `CUSTOMER` and
  `PROJECT` appear only in the SO table above.
- **AC-R2-02 [BE]** Given a settled line whose qty moved 182 to 214, when it prints, then
  `QTY = 182`, `QTY CHANGE TO = 214`, `DELIVERY DATE CHANGE TO` blank, `REMARK = ORDER 32`.
- **AC-R2-03 [BE]** Given a settled line whose date moved 01/09/2026 to 01/04/2027 and qty did
  not, when it prints, then `QTY = 280`, `QTY CHANGE TO` blank, `DELIVERY DATE = 01/09/2026`,
  `DELIVERY DATE CHANGE TO = 01/04/2027`, `REMARK = DELAY`.
- **AC-R2-04 [BE]** Given a cancelled line (kind `cancelled`, old qty 280), when it prints, then
  `QTY = 280`, `QTY CHANGE TO = 0`, `REMARK = CANCEL BALANCE 280 NOS`.
- **AC-R2-05 [BE]** Given a plain raised line, when it prints, then `QTY = 214`, both CHANGE TO
  cells blank, `REMARK = ORDER`.
- **AC-R2-06 [BE]** Given an amendment-derived DELAY or ADVANCE row (from `derive_for_amendment`
  with a `from_value` date), when it is recorded for the handover, then `was.delivery_date` is
  the previous date and the REMARK is the bare verb (`DELAY` / `ADVANCE`), never `- Was
  2026-09-01`.
- **AC-R2-07 [BE]** Given any date reaching the email (line cells, `was`, remark notes, the
  `today` stamp), when rendered, then it is `dd/mm/yyyy`. Specifically `_change_note` writes
  `Was 01/09/2026`, not `Was 2026-09-01`, and the same string is what the OI worklist note shows.
- **AC-R2-08 [BE]** Given the existing seeded template row (`email_templates.code =
  order_inquiry_handover_default`) exists on the target DB, when the migration runs, then its
  `subject`, `body_html` and `body_text` are UPDATED in place to the r2 layout, and a second run
  is a no-op. A DB without the row gets it inserted. Downgrade restores the r1 body.
- **AC-R2-09 [BE]** Given `<s>` was the r1 change marker, when the r2 template renders any line,
  then no `<s>` tag appears in `body_html`.

### S2 Named-path equality gate

- **AC-R2-10 [BE]** Given a NAMED line (not carried) whose only live row is a plain `raised`
  ORDER row with no links, same verb, same qty and same delivery date as the new need, when
  `refresh_for_decision` runs, then the row is kept (same id), its `supply_decision_id` moves
  to the new revision, no row is cancelled, no row is raised, and NO handover line is recorded.
- **AC-R2-11 [BE]** Given the same shape but the new need differs (qty 280 to 300), when it runs,
  then the row is settled in place (same id, qty 300, `previous_qty` 280) and ONE handover line
  of kind `settled` is recorded (`QTY 280`, `QTY CHANGE TO 300`, `REMARK ORDER 20`), not a
  cancel + a raise. `test_named_line_reconfirmed_new_qty_prints_cancel_and_order` is rewritten
  to this expectation.
- **AC-R2-12 [BE]** Given the named line's live row has a different verb (ORDER_BACK vs ORDER)
  or the line carries two live rows, when it runs, then today's supersede path runs unchanged
  (cancel + raise, two handover lines).
- **AC-R2-13 [BE]** Given SO314594's rev-2 shape on a prod-copy fixture (four plain raised rows,
  four cascade-drafted rows, two new lines), when a full re-confirm names all lines, then the
  email carries exactly two lines (the two new ORDERs) and the four plain rows keep their ids.

- **AC-R2-16 [BE]** Given a Confirm on an order that has still-raised amendment rows (rows on an
  inquiry with `amendment_id` set, state `raised`, verb DELAY / ADVANCE / CANCEL BALANCE / CHANGE
  SO), when the handover email for that Confirm builds, then those rows are appended to the line
  table after the Confirm's own lines, printed as `kind="raised"` lines with `was.delivery_date`
  (or `was.qty`) from `previous_delivery_date` / `previous_qty` when set, else from the note's
  `Was dd/mm/yyyy`, verb in REMARK. Each such row is printed at most once per email.
- **AC-R2-17 [BE]** Given the amendment rows were already printed by their own publish email, when
  the next Confirm on the order prints them again, then this is by design (owner ruling Q4,
  18 Sep): purchasing reads one page per Confirm. A Confirm on an order with no still-raised
  amendment rows appends nothing.

### S3 Subject location

- **AC-R2-14 [BE]** Given the lines of one email carry `stock_location` values `{"BRW-IR",
  None}`, when the subject builds, then it is `OI: BRW-IR @ SO314594`.
- **AC-R2-15 [BE]** Given `{"BRW-IR", "SEL", None}`, then the subject is `OI: SO314594` (mixed
  stays bare). Given `{None}` only, then bare.

### S4 Depth-N undo (journaled revisions)

- **AC-R2-20 [BE]** Given a confirm supersedes rev N-1, when the new journal attaches, then rev
  N-1's `undo_journal` is left as it was (not cleared).
  `test_attaching_a_journal_clears_the_superseded_decisions_journal` and
  `test_supersede_clears_journal_to_sql_null` are rewritten to assert it is kept.
- **AC-R2-21 [BE]** Given an undo reinstates rev N-1, when it commits, then rev N-1's journal is
  kept and the board's `undo` for that order now names rev N-1 with `mode = "journal"`.
  `test_after_an_undo_the_reinstated_revision_is_not_undoable` and
  `test_undo_clears_reinstated_journal_to_sql_null` are rewritten.
- **AC-R2-22 [BE]** Given two journaled revisions, when undo runs twice, then the order has no
  active decision, both journals' drafts are back, both undone emails were sent, and a third
  undo is refused (`nothing to undo`).
- **AC-R2-23 [BE]** Given a journal `update` entry, when the confirm writes it, then the entry
  also carries `new`: the values written for the same keys as `old`.
- **AC-R2-24 [BE]** Given a journaled row whose current value differs from the entry's `new`
  for any journaled key (another writer touched it since the confirm), when undo is parked,
  then the park answers 409 with `refusal = "changed"` and names `table` and `pk`; nothing is
  replayed. A row whose current value equals `new` does not refuse.
- **AC-R2-25 [BE]** Given a legacy journal entry without `new` (written before this lane), when
  undo runs, then the `changed` check is skipped for that entry and the replay proceeds as
  today.
- **AC-R2-26 [BE]** Given rev 2's undo restored a row to rev 1's post-image, when rev 1's undo
  runs its `changed` check, then it passes (rev 2's `old` equals rev 1's `new` by construction).
- **AC-R2-27 [BE]** Given the board read, when `undo` is built, then `BoardUndo` carries `mode`
  (`journal` | `reconstructed`) and `refusal` may be `changed`; `board_undo_map` still loads only
  the trimmed journal (no full-journal deserialisation added).

### S5 Reconstructed undo (journal-less revisions)

- **AC-R2-30 [BE]** Given an ACTIVE decision with `undo_journal IS NULL`, when the board read
  builds `undo`, then it is present with `mode = "reconstructed"` ONLY for a user whose role is
  `superadmin` or `admin`; other users get `undo = null` for that order.
- **AC-R2-31a [BE]** Given an order with amendment-raised rows (`amendment_id` set, no
  `supply_decision_id`), when a reconstructed or journaled undo runs, then those rows are untouched.
- **AC-R2-31 [BE]** Given a reconstructed undo of decision D (previous P or none), when it
  commits, then:
  a. every `order_inquiry_rows` row with `supply_decision_id = D.id` created after P's
     `confirmed_at` (or within 60 s before D's `confirmed_at` when there is no P) is deleted with
     its links; orphaned claims are freed;
  b. every remaining row with `supply_decision_id = D.id` is repointed to `P.id` (or NULL);
     when its `changed_at` is within 60 s of D's `confirmed_at` its `qty` and `delivery_date`
     are restored from `previous_qty` / `previous_delivery_date`, those two are set NULL, and
     the note gets `; restored by reconstructed undo of revision N` appended;
  c. every row in state `cancelled` whose note is `Superseded by revision N` (N = D's) is set
     back to `raised` with the note appended `; reinstated by reconstructed undo`;
  d. every row with `redirected_to_pool = true` whose note contains `released at revision N`
     is set `redirected_to_pool = false`;
  e. `so_line_allocations` with `decision_id = D.id` are deleted; `stock_transfers` with
     `supply_decision_id = D.id` in state `proposed` are deleted, and those cancelled with
     `cancelled_reason = "Superseded by revision N"` return to `proposed` under `P.id`;
  f. D is deleted with an audit delete row (same as the journal undo); P becomes `active`
     with `superseded_at` / `superseded_reason` NULL;
  g. no draft is written (nothing to restore);
  h. an `order_inquiry_undone` email is sent with headline `RECONSTRUCTED` and one line per row
     removed or restored.
- **AC-R2-32 [BE]** Given a reconstructed undo, when a row of D has a link with `linked_at >
  D.confirmed_at` and `auto = false`, or a row in state `actioned` with `actioned_at >
  D.confirmed_at`, then the park answers 409 with the existing `linked` / `actioned` refusal.
- **AC-R2-33 [BE]** Given SO314594 and SO314593 on the 0915_1900 prod copy brought to their
  17 Sep state (fixture built from the two revisions' `line_snapshots` and the OI rows as
  queried on 17 Sep), when reconstructed undo runs twice on each and a full confirm follows with
  the two rejects re-entered, then: the OI rows equal the 10:11 email's set plus the two new
  ORDER lines, no cancel + order pair, SRTWCX8605-S-RL-PJ prints `182 | 214 | ORDER 32`, and
  exactly one handover email per order is queued.
- **AC-R2-34 [BE]** Given the reconstructed action, when parked, then it uses action key
  `project_sales_order.undo_confirm` with payload `{decision_id, mode: "reconstructed"}`; the
  server refuses (409) a `mode` that does not match the decision's journal state.
- **AC-R2-35 [BE]** Given a user without the admin role, when they park a reconstructed undo by
  hand-crafting the payload, then 403.

## Phase 3

- **AC-R2-E01 [E2E]** agent-browser on the lane stack, sidebar navigation from `/`: a two-order
  board with one journaled order and one journal-less order (as admin) shows both gear entries
  with the right wording; pressing the journaled one runs the countdown and, after commit, the
  gear offers the reinstated revision. Screenshots at 1280 and 375.
- **AC-R2-E02 [E2E]** The seeded email, rendered on the lane stack for a settle + a delay + a
  cancel + a plain raise, matches AC-R2-02 to AC-R2-05 cell for cell (screenshot of the outbox
  HTML in the browser).
- **AC-R2-T01 [T]** Kill test on AC-R2-10, AC-R2-20, AC-R2-24 and AC-R2-31c.

## Explicit no-motion list

The gear menu, the countdown fill and the toast are existing primitives; nothing new animates.
