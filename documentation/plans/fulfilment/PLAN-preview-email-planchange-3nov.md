# PLAN: Confirm preview email equals the purchasing email on the planning-change path

Status: implemented (small fix track: tests only, no migration, no auth change)

Lane: PREVIEW-EMAIL-PLANCHANGE. Owner rule: email = preview = attachment, all three tally
(see `PLAN-confirm-preview-stale-2nov.md`).

## Report

On the `_form_three` fixture (`tests/test_planning_change_apply_on_board.py`), with another
order's raised awaiting row and an open pool PO line added, crew observed (PR #2128 crew-note):

1. The confirm-all dry run's `email_lines` held ADVANCE, ORDER 25 and one CANCEL ALL. The real
   press sent ADVANCE, ORDER 25, CANCEL ALL, CANCEL ALL.
2. A dry run followed by the press in one session made line 1 read ORDER 15.

## Finding: test-harness artifact, not a production defect

- Production registers the order-inquiry post-commit listeners at startup
  (`register_order_inquiry_post_commit_dispatch`, `app/main.py:380`). They drain the handover
  queue (`session.info["oi_handover_pending"]`) when a root transaction commits, discard it on
  rollback, and drop it whole at the end of a dry run (`confirm_preview`). So every write
  starts on an empty queue.
- The planning-change test module never registers them. Its fixture's own earlier confirms leave
  4 stale items on the session queue. `record_saved_lines`
  (`project_order_inquiry_service.py`, the `told` fold over the queue) then folds those stale
  items into the saved line. That changes the write's own output: line 1 reads ORDER 25, and one
  CANCEL ALL is dropped.
- Isolation, on an unregistered session:
  - Popping only `oi_handover_pending` before the dry run gives ADVANCE, ORDER 15, CANCEL ALL,
    CANCEL ALL.
  - Popping `oi_saved_lines_told`, `oi_split_acted_by_order` or `_oi_raise_marker` changes
    nothing.
- With the listeners registered, the dry run, the press alone, and the press after a dry run all
  give ADVANCE, ORDER 15, CANCEL ALL, CANCEL ALL.
  - The dry run leaves nothing behind.
  - The preview already renders through the press's own context builder
    (`_build_handover_context`).
- The same leak explains #2128's "ORDER 25 with the placement pass, ORDER 15 without".
  - With the listeners registered, the pass places (1 row, 1 allocation), and the email reads
    ORDER 15 whether it runs or not.
  - Noted on #2128.

## Change

`tests/test_confirm_preview_email_parity.py` registers the listeners the way production does. It
asserts that the dry run's `email_lines` equal, field for field, the email the press builds
through `build_handover_email` (captured, never dispatched). Cases:

- the planning-change path;
- the press after a dry run;
- an ordinary first confirm;
- an ordinary re-confirm of a grown line.

All four are red without the registration.

No production code change: nothing in production diverges.

## Trigger for more

If a production path is ever found that starts a write on a non-empty handover queue (a session
reused across writes without the listeners), `record_saved_lines` should fold only the current
write's items (the item's `tx` is the current root). Not built now: there is no such path today.
