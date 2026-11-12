# PLAN: OI-WHOLE-SO-CANCEL - whole-SO cancel and SO delete from AutoCount raise a board item

Status: Hand test v2 (built, reviewed twice, browser pass PASS). Track: M. Track: M (LEAD pattern).

## Problem

A whole-header cancel on an AutoCount SO (no Cancel SO document) and an AutoCount SO delete
close every live Order Inquiry row on that SO at sync time without any Fulfilment Planning
board item, so CS never confirms and purchasing never hears. Every other cancel path (Cancel
SO document, one line removed) waits on the board and CS Confirm sends CANCEL.

## Goal

Both events raise a board item for CS, like the other cancel paths. Details follow the
behaviour card answers.

## Facts (re-verified on main 42f418bd)

- `ingest.py:553` calls `diff_lines(before, after)` with no `scope_documents`; `outstanding_diff.py:259-263`
  then derives scope from the AFTER lines only, and `_capture_planning_diff_after`
  (`document_ingest_service.py:1310-1340`) skips cancelled lines, so a wholly cancelled SO is out of scope.
- `deletion_service.py:600-630` cancels the header and lines and calls `flag_rows_for_cancelled_lines`; no
  planning-change hook.
- Board gate and Confirm path already exist: `planning_change_service.build_batch` (`:971`, kind
  `cancelled` from `_map_kind` `:802`), Confirm retires via `_retire_inquiry_rows` (`:4122-4180`, called at
  `:4972-4977`).

## Change

1. `ingest.py` `_run_planning_change_hook`: pass `scope_documents=set(service.so_header_id_by_number)`
   (every SO this push wrote, captured in `_capture_planning_diff_after`).
2. `deletion_service._deactivate` for `sales_orders`: capture before lines (same shape as
   `_capture_planning_diff_before`), and after the cancel call `planning_change_service.build_batch` with an
   empty after side and that SO as scope. Best effort like the ingest hooks.
3. Q1 (b): a whole-header cancel and the delete stop calling `flag_rows_for_cancelled_lines` for SO lines.

## Standing rules that apply

- Notification only when the receiver has something to do (no email at sync; CS Confirm only).
- One bad line never fails a batch (hooks best effort, ingest already committed).
- Plain wording ("Line cancelled" already shown).
- Every action tracked shows in History (OI_ROW_CANCELLED audit on Confirm, existing).

## Built (12 Nov)

- Ingest scope = `service.so_numbers` (only records that succeeded), `ingest.py:556`.
- SO delete raises the batch, `deletion_service.py` `_raise_so_cancel_batch`; one line shaper
  `planning_diff_line` in `document_ingest_service.py`.
- Board / list (browser pass found CS could not reach the item): `_cancelled_pending_change_rows` admits a
  cancelled header; `_cancelled_pending_arm` in `project_so_reconciliation_service.py` lists a cancelled SO only
  while it has a pending cancelled change; `_standings` seeds the order so Confirm posts; confirm-all results
  carry `so_number`; `FulfilmentBoardPanel.tsx` renders the List view + Confirm when the only lines are pending
  cancelled ones.
- Q1 seam: superseded by v2 (owner rule 12 Nov): the switch and the sync-time auto-done for a
  whole-SO cancel / SO delete are removed; rows wait for CS (`app/services/oi_waiting_for_cs.py`).
- Not in scope, noted: a sidebar click to Fulfilment Planning while a board is open keeps the board on screen
  until a reload (pre-existing, not touched here).

## v2 built (12 Nov)

- One rule: any AutoCount change since CS's last Confirm reads "Waiting for CS" on the OI screens (derived,
  `app/services/oi_waiting_for_cs.py`); purchasing cannot acknowledge it (409; Confirm skips it with a notice);
  the system auto-confirm skips it; CS Confirm clears it and the batch's rows are auto-confirmed after apply.
- The 30 Oct auto-done at sync is removed (header cancel, SO delete).
- OI header reads "Waiting for CS" (not Completed) and its to-confirm count leaves waiting rows out.
- Lines list: a Status column (Waiting for CS > SO cancelled > Line cancelled > ack text), sorted server side.
- Qty: one-row line shows the SO's qty with Was while waiting; multi-row shows SO Qty Was.
- A change back to the confirmed values retires the pending row unless location or item still differ.
- Exports: owner exception, NEITHER OI export changes (AC-V2-6 FINAL).
