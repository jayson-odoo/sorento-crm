# PLAN - Undo last confirm on the fulfilment planning board

Status: BUILDING, 17 Sep 2026, owner aligned on the Lavish page (Q1 no rewind, Q2 restore); tickets #977 to #981; branch `feat/board-undo-last-confirm`. UAC: `board-undo-last-confirm-acceptance-criteria.md`. Backlog BL-063. Research: `research-board-confirm-write-set-17sep.md`.
Domain: SCM, fulfilment planning / order inquiries. Branch: from `feat/oi-replan-received-links` (#973) until it merges, then re-based onto main.

## The problem, measured

On 16 Sep the owner confirmed SO314595 on the dev copy (revision 1, five rows handed over),
then wanted it back. The only reverse today is Reset planning
(`app/services/scm/planning_reset_service.py:36`): it hard-deletes every revision, every OI
row, link, claim, allocation and transfer of the order, unconditionally. There is no path that
reinstates a superseded revision; every existing "un-decide" mints a new forward revision
(`_reissue_without_line`, `uncover_lines`, `supersede_for_material_change`).

What one Confirm writes today, and what is lost (research note, sections 1 and 2, both passes):

| written | addressable after the fact | pre-image today |
| --- | --- | --- |
| `so_supply_decisions` new row, previous row superseded | `supersedes_id` | recoverable, audited |
| `so_line_allocations`, `allocation_claims`, new `stock_transfers`, raised `order_inquiry_rows` | `decision_id` / `supply_decision_id` | deletable |
| `order_inquiry_links`, `scm.order_link_claim` removed on settle / redirect | no | LOST, hard delete |
| `so_supply_decision_drafts` of the named lines | no | LOST, hard delete |
| settled row `note`, `previous_qty`, `previous_delivery_date`, `ack_state`, `acknowledged_*`, `supply_decision_id`, `actioned_*` | no | LOST, overwritten |
| cancelled row `note` (three bare assignments), shrunk row `qty` | no | LOST |
| kept `stock_transfers.supply_decision_id` repoint, `sales_order_lines.stock_location` | no | LOST |
| `planning_change_rows.applied_state` / `result_json`, `planning_change_batches.applied_*` (batch fork) | batch id | `applied_state` yes, `result_json` LOST |
| donor order re-issue (`_reissue_without_line`) | donor's `supersedes_id` | recoverable, second chain |
| handover email, changed-with-links automation, task, in-app notification | no | fired post-commit, irreversible |

Fifteen tables, two forks (plain confirm and planning-change apply), one of them touching a
second order. A hand-written "reverse each table" service would have to know every one of
these sites and every future one. The owner ruled exact restore (R2).

## The design: journal on the way in, replay on the way out

One seam. Every board Confirm runs inside a journal that records, at each flush, what the
unit of work is about to do. Undo replays that journal backwards. Nothing in the undo service
knows a table name.

### Capture

`app/services/project_supply_undo_service.py`, `class UndoJournal`:

- A context manager that attaches a `before_flush` listener to the session and detaches it on
  exit. Per flush it records, for every object in `session.new`: `("insert", table, pk)`; in
  `session.dirty` with real changes: `("update", table, pk, {column: old value})` using
  `attributes.get_history` (only changed columns, old side); in `session.deleted`:
  `("delete", table, pk, {every column: value})`. Values serialized by the audit listener's
  own serializer (`app/services/audit_service.py:338-392`, it already handles UUID, Decimal,
  date, JSONB), so the two never drift.
- Entries keep capture order and a flush sequence number.
- On exit the caller passes the decision the confirm minted; the journal is written to the
  new column `so_supply_decisions.undo_journal` (JSONB, nullable). One column, no table
  (PRINCIPLES: one preference does not need a table). The decision row's own insert is in
  the journal; that is correct, replay deletes it.
- The seam is the two board routes only, `app/api/v1/projects/fulfilment_planning.py`:
  `confirm_supply` (`:599`, both forks at `:621-624`) and `write_one` inside `confirm_all`
  (`:422-428`, one journal per order because `confirm_many` runs one savepoint per order).
  A revision minted anywhere else (`uncover_lines` after a rejection, `_reissue_without_line`
  as a donor's own newest, a script) has no journal and is not undoable. That is the R1
  rejection case for free: a purchasing rejection writes an unjournalled revision on top.
- The journal must see the final flush: the context manager calls `db.flush()` before
  detaching.
- Post-commit dispatchers (`_fire_pending_handover`, `_fire_pending_changed_with_links`,
  `_fire_pending_purchasing_notifications`) are not journalled; they already ran.

### Undoable

Board payload (`app/services/project_fulfilment_board_service.py`, order header) gains
`undo: {revision_no, confirmed_at, confirmed_by_name, refusal} | null`:

- null when the order has no active decision, or its active decision has `undo_journal` NULL.
- `refusal` is null, `"manual_link"` or `"actioned"`, from one query over the order's OI rows
  and links: any `order_inquiry_links` row with `auto = false AND linked_at > confirmed_at`
  on a row of this order's inquiries, or any `order_inquiry_rows` with `state = 'actioned'
  AND actioned_at > confirmed_at`. Time, not actor, separates purchasing's work from the
  confirm's own step-3 borrow link (which is `auto=False` but `linked_at` inside the confirm
  transaction, so not later than `confirmed_at`; Postgres `now()` is constant within a
  transaction). The same predicate is the service's guard (one rule, one place: the board
  reads it, the undo re-checks it at commit).

### Replay

`undo_last_confirm(db, order, *, actor_user_id)` in the same module:

1. Load the active decision; 409 `no_journal` if `undo_journal` is NULL; 409 `superseded`
   if `decision.id` differs from the id the pending action was created with; 409
   `manual_link` / `actioned` per the predicate above.
2. Replay in three passes over the journal:
   - deletes of `insert` entries, in reverse capture order (children before parents, since
     the unit of work inserted parents first);
   - re-insert of `delete` entries, in capture order reversed within each flush and flushes
     reversed (parents before children: the unit of work deleted children first);
   - restore of `update` entries in reverse capture order, skipping any pk that was in the
     `insert` set (already gone). A row deleted later in the confirm and updated earlier is
     re-inserted with its at-delete values first, then the earlier update restores the older
     values on top, because updates replay after re-inserts.
   Core SQL through `Base.metadata.tables[table]` (insert / update / delete by pk), not ORM
   objects, so no listener (audit, embedding, handshake) re-fires on the way back except the
   `SOSupplyDecision` audit DELETE, which is wanted (AC-UC-29).
3. Set `undo_journal = NULL` on the reinstated previous decision (R3: one step, once). Revision
   1 has no previous decision; nothing to clear.
4. Record the undo email event (see below), flush, return `{revision_no, restored_to}`.

Why core SQL and not ORM: the ORM would run `refresh_link_state`, handshake stamps and the
embedding listeners on rows it re-inserts, which is exactly the drift R2 forbids.

Why time and not actor for the refusal: the CS planner and the buyer can be the same person
at Sorento; `linked_by` cannot tell them apart, `linked_at > confirmed_at` can.

### The pending action

`app/services/record_actions.py`: register
`FormAction(key="fulfilment_planning.undo_confirm", entity_types=("project_sales_order",),
window=WINDOW_REVERSIBLE, permission="projects.projects.edit", execute=_undo_confirm)`.
`payload = {decision_id}` captured at creation so a Confirm written during the countdown is
detected (AC-UC-28). The shared routes `POST /pending-actions`, `/cancel`, `/current`
(`app/api/v1/system/pending_actions.py`) need nothing new. The scheduler sweep
`form_action_commit` commits an undo nobody is watching.

### The email

Same method as #962, copied not adapted:

- `app/services/automation_triggers.py`: `TriggerSpec(type="order_inquiry_undone", label=
  "Order inquiry undone", config_schema={})`, pull evaluator returns `[]`.
- `project_order_inquiry_service.py`: `_record_undo(...)` appends to `Session.info` key
  `oi_undo_pending` with `tx` / `tx_chain` from `_transaction_chain`; the existing
  `register_order_inquiry_post_commit_dispatch` gains the third triple (`after_commit` mark,
  `after_transaction_end` fire on a fresh `SessionLocal()`, `after_soft_rollback` discard),
  each a copy of the handover one with the key swapped. Context: `{undo: {so_number, customer,
  project, revision_no, lines: [{item_code, qty, delivery_date, outcome}], link}, actor,
  today}`; `outcome` per line is `back to <qty> on <date>` or `removed`, read from the
  journal's OI row entries.
- Migration `undo_0001_seed_undone_automation`: template `order_inquiry_undone_default`
  (subject `OI undone: {{ undo.so_number }} rev {{ undo.revision_no }}`, inline-styled HTML
  and text bodies, same style as `oihe_0001`), automation "Order inquiry undone", enabled,
  `recipient_config` copied from the handover row at migration time (purchasing roles,
  `include_actor`, `one_email`), idempotent by existence, downgrade removes the row then the
  template if unreferenced.

### Frontend

- `FulfilmentBoardPanel.tsx` gear menu (`:1371-1402`): after "Undo all", one
  `DropdownMenuItem` per order whose `undo` is non-null, label `Undo <SO> confirm (rev N)`,
  disabled with `title` when `refusal` is set. Selecting it calls
  `useDeferredAction({actionKey: 'fulfilment_planning.undo_confirm', entityType:
  'project_sales_order', entityId, verb: 'Undoing', subject: soNumber, payload: {decision_id},
  invalidateKeys: [board query key]})`.
- The Confirm button slot (`:1403-1416`) becomes `DeferredActionButton` with the Confirm
  button as `idle`: while an undo is pending the countdown sits where Confirm was, Cancel
  beside it, Escape ignored (`components/common/DeferredActionButton.tsx` as is).
- Service: `fulfilmentPlanningService.ts` needs nothing; `services/pendingActionService.ts`
  is the call. Phase 1 mocks `undo` on the board fixture and the three pending-action calls.
- No new motion. Reuses `DeferredCountdown` and the dropdown preset. Nothing else animates.

### Permissions and scope

Create pending action: `projects.projects.edit` (Confirm's own slug, `fulfilment_planning.py:73`).
Order lookup through `ProjectSupplyService.get_order` under company scope, so a foreign
company gets 404 before any check. Admin may cancel another user's countdown (existing rule).

## Rulings taken on the Lavish page

- Q1 RULED 17 Sep (Lavish page): no book rewind. Undo returns the batch to pending and leaves
  the book where AutoCount put it; Reset planning keeps its rewind checkbox for UAT.
- Q2 RULED 17 Sep: SO314595 on the dev copy is restored from the 15 Sep dump (pre-lane
  revisions have no journal; the plan does not backfill journals).

## Not in this lane

- Undo of a donor order's own newest revision when that revision was minted by another
  order's confirm (the donor sees no journal; its planner uses the other order's undo).
- Redo. A second Undo. A revision history drawer (none exists; BoardDecidedMarker and
  SupplyCompositionSection show the current revision only).
- Un-sending the handover email; the undo email is the compensation.
- `uncoverChangedLines` stale-snapshot keys (BL-065).

## Slices

- S0 (#977) [FE, Phase 1] gear entries + countdown in the Confirm slot, mocked `undo` and
  pending-action calls; browser evidence at 375 and 1280. AC-UC-01..09.
- S1 (#978) [BE] migration `undo_0001` column `undo_journal`; `UndoJournal` capture at the two
  routes; board payload `undo` with the refusal predicate. AC-UC-10..15.
- S2 (#979) [BE] `undo_last_confirm` replay, the record action, refusal at commit, journal clear.
  AC-UC-16..31. Tester first; kill tests AC-UC-42.
- S3 (#980) [BE] `order_inquiry_undone` trigger, `_record_undo`, post-commit triple, seed migration
  (same `undo_0001` file or `undo_0002`). AC-UC-32..35.
- S4 (#981) [E2E] on `sorento_ai_automation_0915_1900`, SO314593. AC-UC-40..41. Then reviewer +
  security reviewer (auth + RBAC surface, Opus) + guide.

## Testing seams (agreed before Phase 2)

- Journal capture is tested through the two routes, not the class: confirm, read
  `undo_journal`, assert entries by (table, pk).
- Exact restore is tested by snapshotting the seven tables to dicts before Confirm (helper in
  the tester's file, keyed by pk, `updated_at` dropped) and asserting equality after undo.
- Refusal is parametrized over the three arms (manual link after, actioned after, step-3
  link inside) so one rule at one seam serves every arm.
- Email: `_captured_dispatches` monkeypatch from `tests/test_order_inquiry_handover_automation.py:99`.
- Seed chain: `tests/test_so_supply_confirmation.py` builders in their documented order;
  batch fork through `tests/test_planning_change_apply_on_board.py` helpers.

## Migration note

`undo_0001_undo_journal` parents onto the lane head (`512_committed_v_redirect_exclude`)
while branching from #973; `./scripts/alembic-reparent.sh` after #973 merges and again before
PR. Revision id under 32 chars.
