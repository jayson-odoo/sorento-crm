# PLAN: purchasing email has exactly one trigger (board Confirm)

Status: Plan (behaviour card posted, waiting on owner answers). Track: M, LEAD pattern.

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
| S2 | "Apply planning changes" standalone route | `planning_changes.py:98` -> PCS `apply` (same as K4) | handover | STOP (no frontend caller: `planningChangeService.ts:113` defines it, nothing imports it) |
| S3 | "Send to purchasing" resend button | `order_inquiries.py:1490` -> `oi_handover_resend.py:175` `build_handover_email` + `send_match`, which runs even when the automation is switched off (`automation_service.py:339-345`) | handover | STOP (Q3) |
| S4 | Project sales "Publish amendment" | `projects/sales_orders.py:894` -> `project_so_delta_service.py:844` -> POI:7662 `derive_for_amendment` -> `_write` | handover | STOP (Q4) |
| S5 | Purchasing Reject uncovers the CS confirmation | POI:10045 `_uncover_rejected_lines` -> PSS:8321 `uncover_lines` -> `_retire_uncovered_rows` | handover to purchasing about purchasing's own reject | STOP |
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

`purchasing_handover_scope(db)`: a context manager entered ONLY by the two board Confirm route
handlers (FP `confirm_supply`, FP `_run_confirm_many`'s per-order write). `_record_handover` and
`_dispatch_changed_with_links` queue nothing outside it (a log line names the dropped kind and row), so
every other path above stops by construction, with no per-path `notify` flags. The `notify` flag on
`retire_rows_for_removed_so_lines` retires with it.

## Open questions

Posted as the crew-ask on the PR; answers recorded here.

## Steps
1. Behaviour card (above), owner answers.
2. Gate, red tests first per path, kill test, reviewer.
