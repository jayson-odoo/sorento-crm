# PLAN: OI reserve on any row that is not Done (OI-RESERVE-ANY-ROW)

Status: Review (small fix track: no migration, no auth/RBAC change, no new ingest surface)

crew-lane: OI-RESERVE-ANY-ROW. UAC: `oi-reserve-any-row-05nov-acceptance-criteria.md` (alongside).

## Ruling (owner, 5 Nov 2026 ~10:25 MYT, verbatim)

"obviously a delay row is reservable ... any row that is not Done are reservable ah, doesn't
matter the Delay or Advance or not, isn't that the current behaviour already?"

## Today (main 2adb19b7)

- Server refuses a reserve REQUEST on anything but ORDER / ORDER_BACK rows
  (`order_inquiry_reserve_service.py` `_REQUESTABLE_VERBS`, `create_request`, code
  `reserve_request_wrong_verb`).
- The stock debt snapshot drill's `requestable` flag reads the same verb list
  (`stock_debt_snapshot_service.py` `_oi_now`).
- Frontend mirrors it (`reserveEligibility.ts` `reserveIneligibleReason`).
- The OI Lines grid sums Reserve requested / Reserved from buy rows only
  (`orderInquiryHeaderLinesColumns.tsx` `lineReserveQty`), Taken from buy rows only and the
  line's reserve pill / actions address the reserve-bearing BUY row only
  (`orderInquiryLineFold.ts` `pickPrimary`, `buildLine`). A request on a DELAY row showed in
  the State pill (the DELAY row was the line's only live row) but "-" in the columns.
- The reserve STEP (`commit_request`) and the reserve emails have no verb check: they already
  work on any row.
- Live case OI-2609-0257 SRTSA830-PJ: PR #2160's repair moved request #2 (33) onto the live 33
  DELAY row.

## "Done", from the existing state model

A row's supply `state` is one of `raised` / `partly_linked` / `placed` / `actioned` /
`cancelled` (`app/models/project_so.py` `INQUIRY_*`). The screen word for `actioned` is
**Done** (`OrderInquiryVerbPill.tsx` `STATE_LABEL`, "the ONE map every reader of the state must
read off"). `cancelled` is history (`oi_row_visibility`). The three states left are exactly
`INQUIRY_LINK_STATES`, "the states a row's LINKS decide" - the row is still open.

Not the handshake's "Done" (`ack_state = acknowledged`, `orderInquiryAck.ts` `ACK_LABELS`): under
OI-AUTO-CONFIRM a non-buy row (DELAY, ADVANCE, ...) is acknowledged automatically
(`oi_auto_confirm_backfill.compute_done`: `row.verb not in BUY_VERBS` is done), so that reading
would make every DELAY row unreservable, the opposite of the ruling.

## The one rule

A row is RESERVABLE when it is live (not cancelled, not used: `oi_row_visibility.is_live_row`)
and its state is in `INQUIRY_LINK_STATES` (not Done). Any verb.

- Backend: `oi_row_visibility.is_reservable_row(row)` + `reservable_row_clause()` (SQL twin).
  `create_request` keeps its specific refusals (used row, wrong state) and drops the verb check.
  The snapshot's `requestable` and the repair script's target selection read it.
- Frontend twin: `isReservableInquiryRow` in `orderInquiryLineFold.ts`, next to
  `isLiveInquiryRow`; `reserveIneligibleReason` reads it (verb message removed).

Requestable quantity is unchanged (`_requestable`: qty - open links - reserve links - bundled).

## Both rows live on one line (review B1, owner ruling (b))

The reviewer asked whether a DELAY row beside its line's live ORDER row should take a reserve
(asking twice for one line). Owner, 5 Nov ~10:40 MYT: "I would rather make it more lenient":
no line restriction. The shape is legacy: since S2 (`PLAN-board-oi-mechanical-22sep.md`) a date
move on a line with a live buy row stamps that row (`_stamp_date_move`) instead of raising a
DELAY row beside it, and `scripts/fold_oi_date_notices.py` folds older duplicates. Where it
still exists, each row is requestable on its own and the grid counts each reserve once.

## Grid (OI page Lines tab, one line per SO line)

- Reserve requested / Reserved: summed over every live row of the line, any verb.
- Taken: buy rows' links + reserve, plus reserve on any other live row. Requested (the buy rows'
  qty) is unchanged: a DELAY / ADVANCE row restates the line's date, and counting its qty as
  well would double the line where a buy row sits beside it.
- Line pill and reserve actions: the reserve-bearing live row of ANY verb is the line's primary
  (urgency requested > reserved > declined), else today's buy-row rule.

## Out of scope

The worklist (Order Inquiries > Lines, one row per OI row) keeps `-` in Taken / Remaining on a
notice row (AC-B3-3); its own Reserved / Requested reserve columns are per row and already
verb-agnostic.

## Slices

1. Red tests (pytest + vitest) from the UAC, committed alone.
2. Backend rule + callers; frontend rule + fold + columns.
3. Reviewer, browser pass, hand-test script.
