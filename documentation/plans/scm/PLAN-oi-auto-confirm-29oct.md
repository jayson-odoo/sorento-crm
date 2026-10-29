# PLAN: OI rows auto-confirm, OI auto-complete, Confirm / Unconfirm as manual override (OI-AUTO-CONFIRM)

Status: Review fix round 2 - re-review at 81feb5780c: earlier blockers fixed, sweep green (1971/0); open: retired-SPO test gap, cancelled-line actioned rows, reject of a manual host, product read; hand test filed. Track: full (L). Draft PR #1986.

## Owner ruling (29 Oct 2026, ~21:55)

"in the future, I don't want the user to go and confirm or unconfirm the order inquiry. I want
the system to automatically mark the rows as confirm or unconfirm by this definition. If the rows
have PO or rejected or reserved, then it's considered confirmed. And if all the rows in the order
inquiry is confirmed, then the order inquiry is automatically completed. So in the outstanding,
the user will only see from a purchasing perspective, what have I not ordered or reserved or
rejected."

## Today (measured, file:line)

- Row "confirmed" = `order_inquiry_rows.ack_state` in (`acknowledged`, `rejected`);
  `awaiting` / `changed` = To confirm (`app/models/project_so.py:767-782`).
- OI header Outstanding = at least one non-cancelled line with a row in awaiting/changed, else
  Completed (`app/services/order_inquiry_header_service.py:291`, `_rows_agg` 186-241).
- Purchasing's Confirm press = `acknowledge_rows` (`app/services/project_order_inquiry_service.py:9234`).
- Reorder plan counts project demand ONLY on acknowledged/changed rows
  (`app/services/scm/demand.py:383-393`, `:764`, `:848`); awaiting rows are a chip
  (`app/services/scm/reorder_run_service.py:1265-1290`).
- Cascades already link awaiting rows (`include_awaiting=True` on every cascade door,
  `project_order_inquiry_service.py:3863`, `:9251`).
- Links: one target each - PO line, SPO allocation, or confirmed CS reserve
  (`app/models/project_so.py` `OrderInquiryLink`, CHECK at ~1239).

- Manual presses: OI Lines "Confirm (N)" / "Unconfirm (N)"
  (`sorento_crm_frontend/app/(protected)/project-sales/order-inquiries/components/OrderInquiriesClient.tsx:1976`, `:1864`),
  OI detail "Confirm" / "Unconfirm" (`.../order-inquiries/[id]/components/OrderInquiryDetail.tsx:922`, `:828`);
  routes `POST /order-inquiries/acknowledge` / `unacknowledge`
  (`app/api/v1/projects/order_inquiries.py:871`, `:929`). `link-now` (`:1022`) links acknowledged rows only.
- The OI Confirm press sends no email, notification or Excel; it stamps and runs the auto-link
  (`project_order_inquiry_service.py:9234-9318`). Unconfirm writes one audit line (`:9461`).
- Out of scope, unchanged: the board / planning-sheet SO Confirm (CS supply decision). It raises
  the rows and sends the purchasing handover email + Excel + in-app task
  (`project_order_inquiry_service.py:14971`, `:14684`, `:14887`). Reject keeps its own email (`:15257`).

## Owner answers (29 Oct ~22:45)

Q1 b (partial stays To order, N left). Q2 SPO counts (it hangs off a PO, owner's chain OI row ->
SO line -> PO). Q3 a (row loses its PO -> not done, OI reopens). Q4 the reorder plan keeps reading
confirmed rows; the confirm is now set by the system. Q5 yes (reserve chip, companion follows host).
Chain recount: reading AutoCount's SO line -> PO chain directly moves 5 OIs (436 -> 431); the auto-link
already turns that chain into links (`order_inquiry_links.claim_id`), so the rule reads links.

## Architecture

- Layer: backend service. The fact stays where every reader already looks: `order_inquiry_rows.ack_state`
  (about 90 readers: header status, worklist filter, reorder plan legs, demand breakdown, board). The
  system writes it; no reader changes. This is "just automating the confirm" (owner, Q4).
- ONE writer: `ProjectOrderInquiryService.auto_confirm(row_ids)` computes done per row (UAC AC-AC-1..10c)
  from LIVE links (PO line not cancelled, SPO allocation not retired, reserve), `bundled_qty` + host,
  `ack_state = rejected`, `state = actioned`, non-buy verb, `redirected_to_pool`. Done ->
  `acknowledged` (by NULL, at now). Not done and `acknowledged` -> `awaiting`. `awaiting` / `changed`
  not done are left alone; `rejected` is never touched; cancelled rows are skipped.
- Called from the existing single choke points: the end of `refresh_link_state` (every link add/remove,
  reserve, cascade), `derive_bundles` (companion), `mark_rows`, the raise path after its cascade, and the
  CS amendment (settle-in-place) path. A host whose done-ness flips re-evaluates its companions in the
  same call.
- Presses KEPT as manual overrides (owner, mock v1 notes): `acknowledge` / `unacknowledge`
  (`order_inquiries.py:871`, `:929`) also write an override (kind confirmed / unconfirmed, by, at:
  three nullable columns on `order_inquiry_rows`, additive migration). `auto_confirm` leaves a
  manually confirmed row alone, and a manually unconfirmed row alone until a link newer than the
  override arrives; a CS amendment or a reject clears the override. `link-now` takes awaiting rows.
- Reorder plan (Q4 = b): `PLANNED_ACK_STATES` (`scm/demand.py:393`) becomes the To order states
  (`awaiting`, `changed`); the awaiting chip and the SO picker's awaiting count go.
- Backfill: one alembic data migration running the same predicate in SQL (idempotent), checked on a dev
  copy against the card's counts. Held SQL for crew's dev DB (it is an UPDATE).
- FE: labels To order / Done, "N left" on partial rows, reserve chip in the PO column, header Lines
  column "N to order / total", empty state "Nothing to order". Waits on mock approval.

## Slices

1. BE auto-confirm writer + hooks + link-now widening (tests first). (Reserve entry in the links reader
   was reverted in review round 1: rows carry `reserve_label` instead.)
2. Manual override columns + press semantics, reorder plan To order states (Q4 b), backfill data
   migration (tests first, dev-copy check).
3. FE after mock approval (vitest first).
4. Review + security review (ingest hooks, company scoping, override audit) + browser pass + hand test.

## Rule (as built)

See the UAC (`oi-auto-confirm-29oct-acceptance-criteria.md`), AC-AC-1..24. Stored in `ack_state`,
written by the system (the card's first "derive at read time" idea was dropped once Q4 kept the
reorder plan on confirmed rows: about 90 readers stay untouched).

## Card history

Behaviour card filed 29 Oct (crew state file `oi-auto-confirm-card-29oct.md`, kept out of this
public repo because it quotes real OI numbers). Q5 reshaped after crew's link-gap dig: reserve-only
rows are done and show the reserve in the PO column; companion rows follow their host; the 16 stale
rows of issue #1215 become not done at backfill (their stored "On PO/SPO" supply pill stays wrong
until #1215's repair script runs, out of scope).
