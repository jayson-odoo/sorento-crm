# PLAN: purchasing email has exactly one trigger (board Confirm)

Status: Review (built; owner answers Q1-Q5 recorded below). Track: M, LEAD pattern.

## Owner ruling (6 Nov 2026)
"the rule of thumb is, I only want the email to purchasing to have 1 trigger, which is this button"
(Fulfilment Planning dialog, "Confirm N order(s)"). Earlier: "I don't want any auto email sent out from
the system for fulfilment planning".

## Why
SO398322 (4 Nov): AutoCount sync re-keyed a line; SO ingest retired the OI row and auto-emailed
purchasing a false cancel. Re-key matching itself is lane AC-REKEY-SAME-LINE (not duplicated here).

## How the emails are built (static read of origin/main 2cc1b2c5)

Abbreviations: POI = `app/services/project_order_inquiry_service.py`, PSS =
`app/services/project_supply_service.py`, PCS = `app/services/planning_change_service.py`, FP =
`app/api/v1/projects/fulfilment_planning.py`.

Two queues on `Session.info` hold every purchasing email this lane is about, both drained after the
root commit:
- `order_inquiry_handover`: queued by `_record_handover` (POI:4611), drained by `_fire_pending_handover`
  -> `send_handover_groups` -> `AutomationService.dispatch_event`. Recipients proven from the seed
  `alembic/versions/oihe_0001_seed_handover_automation.py:165-182`: every `purchasing%` role plus the
  actor, one email.
- `order_inquiry_changed_with_links`: queued by `_dispatch_changed_with_links` (POI:4535), drained by
  `_fire_pending_changed_with_links`. No seed migration: recipients are whatever an admin set on the
  automation row (not provable without the DB; the gate below covers it either way).
- `order_inquiry_undone`: queued by `_record_undo` (POI:5830), drained by `_fire_pending_undo`.
  Recipients copied from the handover row (`undo_0002_seed_undone_automation.py:14-17,160-168`):
  purchasing.

## Behaviour card: every path that emails purchasing

| # | Trigger (who presses / what runs) | Chain (file:line) | Email | Verdict |
|---|---|---|---|---|
| K1 | Board Confirm, one order or Confirm all | FP:1635 `confirm_supply`, FP:490 `confirm_all` -> PSS:5602 `confirm` -> PSS:7939 `refresh_for_decision` (POI:1654, records at 1850-2619, `_settle_row_in_place` 2818, `_stamp_date_move` 3193, `_restate_product` 3106, `_raise_borrow_shortfalls` 5938) + PSS:5980 `record_saved_lines` -> `_tell_splits` -> `_queue_plan_rows` POI:5229 | handover (+ changed_with_links) | KEEP |
| K2 | Transfer to Cancel SO, inside that Confirm | FP:1551 -> PSS:1358 `cancel_lines` -> POI:6383 `retire_rows_for_cancelled_lines` + `record_cancelled_lines` | handover CANCEL + changed_with_links | KEEP (only as part of K1) |
| K3 | Withdraw a confirmed line, inside that Confirm | FP:1604 -> PSS:8321 `uncover_lines` -> POI:7627 `retire_rows_for_dropped_lines` -> `_retire_uncovered_rows` POI:6440 | handover | KEEP (only as part of K1) |
| K4 | Board Confirm on a board holding a pending AutoCount / planning change batch | FP:1732 `_confirm_a_planning_change` -> FP:1823 PCS `apply` -> PCS:4551 `_apply_one_order` -> PCS:3986 `_retire_inquiry_rows` (4042) + POI:7733 `derive_for_book_change` -> `_write` (7894, 7907) | handover | KEEP (it is the button) |
| S1 | SYSTEM: AutoCount SO push removes a line (SO398322) | `document_ingest_service.py:1756` -> POI:6313 `retire_rows_for_removed_so_lines(notify=True)` -> 6348 retire + 6378 `record_cancelled_lines` | handover CANCEL + changed_with_links | STOP |
| S2 | "Apply planning changes" standalone route | `planning_changes.py:98` -> PCS `apply` (same as K4) | handover | route DELETED (Q2) |
| S3 | "Send to purchasing" resend button | `order_inquiries.py:1490` -> `oi_handover_resend.py:175` `build_handover_email` + `send_match`, which runs even when the automation is switched off (`automation_service.py:339-345`) | handover | KEEP, exception (Q3) |
| S4 | Project sales "Publish amendment" | `projects/sales_orders.py:894` -> `project_so_delta_service.py:844` -> POI:7662 `derive_for_amendment` -> `_write` | handover | KEEP, exception (Q4) |
| S5 | Purchasing Reject uncovers the CS confirmation | POI:10045 `_uncover_rejected_lines` -> PSS:8321 `uncover_lines` -> `_retire_uncovered_rows` | none: already dropped by `_uncover_and_notify_rejection` (POI ~9806, test AC-RJ-9) | already STOP |
| S6 | Board "Undo last Confirm" | `record_actions.py:2542` -> `undo_last_confirm` -> POI:5830 `_record_undo` | order_inquiry_undone | KEEP (Q5) |
| S7 | One-off script | `scripts/oneoff/oi_closed_line_cleanup.py:219` | handover | STOP (falls out of the gate) |

No purchasing email today (traced, kept as they are): PO ingest `release_removed_lines` (POI:6246,
"no email", no `_record_handover` inside); `flag_rows_for_cancelled_lines` (POI:1181, "nothing queued
for purchasing"); `auto_confirm_rows_on_po_lines` / `auto_confirm` (POI:1147, 10384);
`autocount_cancel_ingest_service.py:821`; `scripts/release_removed_autocount_lines.py:408`
(`notify=False`).

Not purchasing-bound, untouched by default: `order_inquiry_rejected` to the raiser
(`oirj_0001_seed_reject_automation.py:6-7,171-173`, no roles); in-app purchasing notices
(`_fire_pending_purchasing_notifications`, `send_email=False`; PCS:4259); `order_inquiry_reserve_requested`
(purchasing asks CS) and `order_inquiry_reserved` (CS answers the purchasing requester: a reply to
purchasing's own request, not fulfilment planning).

## The gate (one, structural)

`mark_purchasing_email_trigger(session)` (POI) marks the ROOT transaction the session is in. Two
callers, both a person's press:
- the board Confirm: `fulfilment_planning._confirm_with_possible_rejects`, the seam both Confirm
  routes share (K1-K4);
- Publish amendment: `projects/sales_orders.publish_amendment` (Q4 exception).

`_fire_pending_handover` sends the handover only when the concluded root transaction carries the
mark (the mark is dropped as that transaction ends, committed or not), and
`_dispatch_changed_with_links` queues only inside a marked transaction. Every other path keeps
writing what it writes and emails nobody, with no per-path flag; the `notify` flag on
`retire_rows_for_removed_so_lines` is gone.

Not through the queue, so untouched by the gate: the "Send to purchasing" resend (Q3 exception,
`oi_handover_resend`) and the Undo last Confirm email (Q5, its own `order_inquiry_undone` queue).

## Owner answers (6 Nov 2026)

- Q1 (a): an AutoCount-removed SO line no longer retires its OI rows at ingest
  (`document_ingest_service.py`, the `retire_rows_for_removed_so_lines` call is gone). The push's
  planning-change batch (`api/v1/external/ingest.py` `_run_planning_change_hook`) carries a
  `cancelled` row for the line, and CS's board Confirm retires the rows and emails the CANCEL
  (`planning_change_service._retire_inquiry_rows`). Tested end to end in
  `tests/test_ac_removed_lines_ingest.py`.
  Trade-offs of (a), until CS presses Confirm (review, 6 Nov): the removed line's rows keep
  their state and ack (crew, 7 Nov: a REMOVED line is left out of `flag_rows_for_cancelled_lines`,
  which would otherwise acknowledge a still-open buy by the system; a Cancel SO document and a
  cancelled header are flagged as before), so purchasing still sees them open; its PO/SPO links
  stay claimed; a draft on the line is not deleted (`delete_drafts_for_lines` ran only in the
  ingest retire). If the post-commit `_run_planning_change_hook` fails, no `cancelled` row exists
  and the rows stay live: the recovery is `scripts/release_removed_autocount_lines.py --apply`.
  If CS declines the `cancelled` row, the rows stay live on a cancelled line.
- Q2 (a): the standalone `POST /planning-changes/{id}/apply` route is deleted (no more AutoCount SO
  book uploads; no frontend caller). The board Confirm applies a batch (K4, still live: every SO
  push builds a batch). Tests that used the route as a harness call the service via
  `tests/test_planning_changes.apply_batch`.
- Q3: "Send to purchasing" resend stays: the owner's manual button, an exception.
- Q4: Publish amendment keeps its email ("not used yet"): an exception, marked in its route.
- Q5 (a): the Undo last Confirm email stays.

## Tests

- `tests/scm/test_purchasing_email_one_trigger.py`: K4 emails; the same apply unmarked emails
  nobody; the apply route is gone; the mark ends with its transaction; Publish amendment marks.
- `tests/test_ac_removed_lines_ingest.py`: S1 push emails nothing; Q1 rows wait for the board;
  the board Confirm retires them and emails one CANCEL.
- `tests/test_oi_closed_line_cleanup.py`: S7 script emails nobody.
- Suites that pin the email's CONTENT through a service call opt in to
  `pytest.mark.usefixtures("as_board_confirm")` (`tests/conftest.py`).
- `tests/test_purchasing_email_tripwire_so_po.py` + `_docs.py`: every ingest scenario (SO line
  removed / added / qty / date / item / re-keyed, header cancelled, PO line removed, PO
  auto-confirm, Cancel SO document, DO, GRN) with the handover and changed-with-links automations
  ON, plus a positive control.
- `tests/test_lessons_learnt_regressions.py` (Postgres-free, the release gate's executing step):
  only the two named callers mark a trigger; every purchasing `dispatch_event`, the
  changed-with-links queue and `send_match` sit behind the one gate (AST; kill: removing either
  gate or adding a bypass dispatch is red); the heavy guards above still exist and name every
  scenario.
- Kill test: with the gate disabled, the unmarked-apply, mark-lifetime and S7 tests fail.
