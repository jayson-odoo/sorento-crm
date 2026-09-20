# PLAN - order inquiries: cancelled lines and used rows are shown, and purchasing confirms them

Status: APPROVED in grill by owner 20 Sep 2026 (rulings C1 to C4). Lane
`feat/oi-cancelled-line-used-confirm`. Tickets next.
UAC: `oi-cancelled-line-used-confirm-acceptance-criteria.md` (AC-CL-1 to AC-CL-20). The journey is
the UAC's first section.

## 0. What the owner saw (prod, 20 Sep 2026, after the rebuild lane #1050 deployed)

- SO314593 CB2828-DIY 90 @ 01/06/2026: an ordinary-looking row on a CANCELLED sales order line.
- SO314594 C-FH12 364 + 364 @ 01/09/2026: two sheet rows that the fallback pass put on the one
  cancelled 728 line (the sheet may split a line across rows); the line's other copy is qty 0.
- The To confirm card does not clear on a second press.
- Used rows and cancelled-line rows never reach To confirm: they are auto-acknowledged.

## 1. Measured before designing (18 Sep 2026 prod copy, and the code on origin/main 2acd08e1e)

- 344 live rows on cancelled lines: 340 `actioned`, 3 `raised`, 1 `placed`; 2 hold a link; 343
  `acknowledged`, 1 `awaiting`. 10 used rows, all `acknowledged`. Buy counts 3 of them (158 pcs);
  `actioned` rows are already outside the cards (`_NOT_OWED_STATES`).
- The worklist never reads the line's status: `order_inquiry_worklist_service._base` (916)
  outer-joins `SalesOrderLine` already (978-984, location fallback) but selects and filters
  nothing on `line_status`; `OrderInquiryWorklistRow` (`schemas/project_order_inquiry.py` 276)
  has no such field.
- `SalesOrderLine.line_status` (`models/order.py` 511) takes `open`, `closed`, `cancelled`.
  `cancelled` is written in exactly two places: `scm/sales_order_service._upsert_lines` (1753,
  1927: a removed or zeroed line that has dependents) and `document_ingest_service._line_status`
  (1694-1715: a cancelled AutoCount document cascades to its lines). The weekly outstanding
  upload only ever writes `closed`.
- What reacts to a cancelled line today: only `planning_change_service._retire_inquiry_rows`
  (3775), when a PLANNER ACCEPTS a batch; it cancels the rows. Nothing reacts to the
  `line_status` write itself. That flow is left alone: a row it cancels is `state = cancelled`
  and already outside every list.
- Handshake: `ACK_TO_CONFIRM_STATES = (awaiting, changed)` (worklist service 123). Importer
  `raise_row` is born `acknowledged` on purpose (import service ~2926, migration 454).
  `_settle_row_in_place` flips `acknowledged -> changed` with `changed_at` (1564). Confirm =
  `POST /order-inquiries/acknowledge` (api 552), by ids or by filter ("select all matching",
  `acknowledge_scope` 1256), permission `projects.order_inquiries.acknowledge`; eligible =
  `awaiting` / `changed` and state not `cancelled`, so `actioned` rows can be confirmed already.
- FE: used-row grey = `rowClassName` `opacity-60` on `redirected_to_pool`
  (`OrderInquiriesClient.tsx` 1830); `used` pill = `QtyAnnotationButton`
  (`orderInquiryWorklistColumns.tsx` ~521-580, `WorklistPill`); checkboxes disabled only for
  `state === 'cancelled'` (964). To confirm card: `onClick={() => setAckFilter('to_confirm')}`
  (1630), never toggles; the other three cards toggle in their caller (1614-1623).

## 2. Rulings (owner, 20 Sep 2026)

- **C1** Every live row on a cancelled line goes to To confirm, the 344 existing ones once
  (backfill) and every line cancelled from now on. All are greyed and tagged.
- **C2** Confirm means "seen": the row stays listed, grey and tagged, leaves To confirm and Buy;
  links stay.
- **C3** Every time a row becomes used (replan, or sheet rebuild) it goes to To confirm; the 10
  existing used rows are backfilled.
- **C4** A cancelled-line row leaves Buy only; with a link it still counts in Purchased /
  Incoming.

## 3. Design - the simplest thing: the existing handshake, no new state, no new table

"Needs purchasing's confirm" already has a representation: `ack_state in (awaiting, changed)`.
Nothing new is stored. Three writers flip it, one reader shows the line's status.

- **3.1 Reader.** `_base` selects `SalesOrderLine.line_status == 'cancelled'` as `line_cancelled`
  through the join it already has; the schema gains the field; the Buy arithmetic in `_kinds` /
  `_stage_columns` (2432-2489) and the `kind = buy` predicate treat a cancelled-line row as owing
  0. Purchased / Incoming untouched.
- **3.2 Writer: a line becomes cancelled.** ONE function
  `flag_rows_for_cancelled_lines(db, core_line_ids)` in `project_order_inquiry_service.py`:
  live rows of those lines with `ack_state = acknowledged` -> `changed`, `changed_at = now`.
  Called from the two write sites, only on the transition (previous status not `cancelled`).
  No listener, no event registry: two call sites, one function.
- **3.3 Writer: a row becomes used.** `_redirect_row_if_received` (1591-1627) flips the row it
  marks used the same way.
- **3.4 Writer: the sheet upload.** `_Raiser.raise_row` is born `awaiting` when the row is a used
  row (`match.used_sibling_id`) or the matched core line is cancelled; otherwise `acknowledged`
  as today.
- **3.5 Backfill.** One alembic data migration (revision id <= 32 chars), plain SQL with
  `__tablename__`s checked: `acknowledged -> changed`, `changed_at = now()` for live rows that
  are used or sit on a cancelled line AND whose `acknowledged_at` is null or earlier than a
  fixed cutoff literal written in the migration (its authoring time). A row purchasing confirms
  after that carries a later `acknowledged_at`, so re-running the statement never flags it again.
  Trigger for anything heavier (a "confirmed after cancel" timestamp): a second event that must
  re-flag a confirmed row. None exists today.
- **3.6 FE.** `rowClassName` greys on `redirected_to_pool || line_cancelled`; a `cancelled`
  `WorklistPill` (plain, not a button) beside the quantity; To confirm card
  `setAckFilter((c) => (c === 'to_confirm' ? ACK_ANY : 'to_confirm'))`. Types + service contract
  comment updated. No motion (dense, high-frequency grid: nothing here animates).

- **3.7 Confirm accepts an `actioned` row (correction, 20 Sep 2026, read on resume).** Section 1
  said `actioned` rows can be confirmed already. That is true of `acknowledge_scope` (worklist
  service 1256: eligible = `awaiting` / `changed`, state not `cancelled`) and FALSE of
  `acknowledge_rows` (inquiry service 4598): its `gone` guard refuses every row whose state is
  not in `INQUIRY_LINK_STATES` (`raised`, `partly_linked`, `placed`) with 422
  `order_inquiry_row_not_open`. 340 of the 344 rows are `actioned`, and "select all matching"
  hands its eligible ids to the same function, so one `actioned` row would 422 the whole press.
  The two seams already disagree; C1 settles it. Change: the `gone` guard refuses only
  `state = cancelled`, the same rule `acknowledge_scope` and the route's docstring state. An
  `actioned` row takes the handshake stamp and nothing else: `_linkable_row_clauses` already
  keeps it out of the cascade (states `raised` / `partly_linked` only). No test names
  `order_inquiry_row_not_open` today.

Known consequence, accepted: a flagged row carries `changed_at`, so the sheet rollback keeps it
(rebuild lane, AC-RB-17). A row the upload raises onto a cancelled line is born `awaiting` with no
`changed_at`, so a rollback + re-upload asks purchasing to confirm it again.

## 4. Order of work (one lane, one PR)

- S1 `[FE]` Phase 1 mock: `line_cancelled` in the mock rows, grey + pill, card toggle; 375 / 1280.
- S2 `[BE]` reader: field + Buy exclusion (AC-CL-1, 4, 5).
- S3 `[BE]` writers + importer birth state + backfill migration (AC-CL-6 to 15).
- S4 journey test, mock swapped to real, vitest, agent-browser run, reviewer + security-reviewer
  (permission route + external ingest touched), guide note, DoD gate.

## 5. Not in scope

- Whether the sheet importer should raise a row on a cancelled line at all (open ruling of
  19 Sep). This lane only makes such rows visible and confirmable.
- Cancelling or unlinking anything on Confirm (C2).
- The Raised at history icon width and the sales order detail Plan action (older small fixes).
