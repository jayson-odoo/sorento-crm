# UAC: OI-RESERVE-ANY-ROW

Plan: `PLAN-oi-reserve-any-row-05nov.md`.

- AC-AR-1: CS can request a reserve on a live DELAY row that is not Done; the request is stored on
  that row.
- AC-AR-2: CS can reserve that request; a reserve link is written on the DELAY row and the
  reserved email context lists the row.
- AC-AR-3: the same holds for an ADVANCE row.
- AC-AR-4: a Done row (`state = actioned`) is refused, whatever its verb
  (`reserve_request_wrong_state`).
- AC-AR-5: a used row (`redirected_to_pool`) is refused (`reserve_request_used_row`), whatever
  its verb.
- AC-AR-6: the stock debt snapshot drill reads a live, not-Done DELAY row as requestable and a
  Done row as not.
- AC-AR-7: the repair script only moves a stuck request to a reservable live row; a Done live
  row holds it for a person.
- AC-AR-8 (UI rule): `reserveIneligibleReason` is null for a not-Done DELAY / ADVANCE /
  RESERVE_AND_ORDER row with something to request; it names "not open for a reserve request" for
  a Done row and "a used row" for a used row.
- AC-AR-9 (grid): OI-2609-0257 shape - line A: used 55 row + live 33 DELAY row carrying a 33
  request; line B: live 22 ORDER row, ack awaiting. Line A reads Reserve requested 33 and the
  State pill "Request to reserve 33"; line B reads Reserve requested 0 and its own status.
- AC-AR-10 (grid): a DELAY row reserved 33 reads Reserved 33 and Taken 33 on its line.
- AC-AR-11 (grid): a line with an ORDER row and a DELAY row carrying the request addresses the
  DELAY row for the pill and the reserve actions.
