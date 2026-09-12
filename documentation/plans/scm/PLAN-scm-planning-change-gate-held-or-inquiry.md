# PLAN: a planning change is raised only for a line someone has decided on

**Status:** IN PROGRESS, 12 September 2026. Captain's call on the local prod copy: 1,307 of
1,308 pending planning-change rows on live sit on lines with no held decision and no inquiry
row, so the `Changed` pill on the SCM Sales Orders list sends the reader to a board with
nothing to re-decide.

**Supersedes** AC-R01's "one row per changed planned line" and AC-R03 ("a changed planned line
WITHOUT an active decision shows Not decided and replan") in `PLAN-so-book-diff-replanning.md`.
Everything else in that plan stands.

## The problem, measured

`build_batch` (`app/services/planning_change_service.py`) keeps a changed line when the SO has a
row in `projects.sales_orders`, i.e. it was adopted onto the fulfilment board. It does not ask
whether anyone decided anything for the line. On the 10 Sep live dump:

| Pending change rows | With a held decision | With an inquiry row |
|---|---|---|
| 1,308 across 15 batches | 1 (SO389799) | 0 |

SO403765: 23 rows, all "No decision holds this line yet, so it simply enters the board at its
new date and quantity." The board already reads the live line. The row tells the reader what
moved but asks for no decision, and the pill on the list reads as work.

## The rule (one sentence)

A changed line produces a planning-change row only when the change can invalidate something a
person committed: the line is frozen in the order's ACTIVE supply decision (`held`), or a
non-cancelled Order Inquiry row exists for it. Otherwise the line is silent and the board reads
its new value directly, exactly as it does for a line that was never adopted.

Consequences, spelled out:

- `added` lines never raise a row (a new line is never held and has no inquiry).
- `closed` / qty / date changes on an undecided line raise nothing.
- A line whose decision was challenged or superseded but still has a raised or placed
  inquiry row DOES raise a row: the inquiry is the commitment.
- A batch with zero kept rows is not created (`build_batch` returns `None`), for all three
  triggers (SO book re-upload, ESB ingest hook, manual SO edit), because all three call the
  one function.
- The `Changed` pill (`SalesOrderService.with_planning_changes`) counts only rows whose
  `applied_state` is `pending`, so a batch whose rows were all superseded shows no pill even
  before its `applied_at` is stamped.

## Changes

1. `planning_change_service._build_row` returns `None` when `held is None and not
   inquiry_rows`; `build_batch` skips those, recounts `order_count` / `line_count` from the
   kept rows, and deletes the batch it flushed when nothing was kept, returning `None`.
2. `sales_order_service.with_planning_changes` adds `PlanningChangeRow.applied_state ==
   pending` to the join filter.
3. Data migration `513_planning_change_gate_backfill`: every pending row on an unapplied
   batch with no `held_json` and no inquiry rows becomes `superseded` with a reason naming
   this migration; a batch left with no pending row gets `applied_at = now()` (no
   `applied_by`, the FE already renders that as applied with no actor) and a `result_json`
   note. Nothing is deleted.
4. Tests updated where they asserted the old rule (`test_planning_changes.py` AC-R03 shape
   test, `tests/scm/test_scm_sales_order_edit_propagation.py` batch-raising tests now seed a
   decision first; one of them flips to "undecided line, no batch").
5. Frontend: no change. The board, `BoardChangeTable` and the pill already read what the
   backend sends.

## Not doing

- No new "date moved" hint on undecided board rows. The board shows the live date; a hint
  would be a second opinion about a value it already shows. Revisit if CS asks.
- No change to the P8a divergence path (ours vs AutoCount's copy). Different mechanism.

## Verification

- pytest: `tests/scm/test_planning_change_gate_held_or_inquiry.py` (new, red first),
  `tests/test_planning_changes.py`, `tests/scm/test_scm_sales_order_edit_propagation.py`,
  `tests/test_ingest_documents_v2_hooks.py`, `tests/test_planning_change_apply_on_board.py`.
- Migration on the lane DB (`sorento_main_12sep`): 1,307 rows superseded, SO403765 loses its
  pill, SO389799 keeps it (1 held row).
- Browser: SCM Sales Orders search SO403765 shows no pill; SO389799 shows the pill and the
  board opens with one Was / Now cell.
