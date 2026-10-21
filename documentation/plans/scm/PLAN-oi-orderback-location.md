# PLAN: OI email ORDER BACK names its refill (donor) location

Status: in review on PR #1815. Track: small fix (no migration, no auth, no UI change beyond the email words); the small fix track has no separate UAC file, the owner's ruling below is the acceptance list.

## Owner ruling (21 Oct 2026 ~11:50 MYT, option A; replaces the 11:40 option B)

- LOCATION and the subject stay exactly as today: the SO line's own location (13/14 Oct rule).
- ONE row per saved line, no splitting ("I already can split manually when I confirm").
- REMARK names the donor of every ORDER BACK part whose donor differs from the row's LOCATION,
  in the `USE <location>` style:
  - SO426913 (ORDER 4 at BRW-IR turned Borrow 4 from BRW-BB): `ORDER BACK BRW-BB, CANCEL ORDER 4`
  - two donors: `ORDER BACK BRW-X 6 & ORDER BACK BRW-Y 4`
  - Use + Borrow: `USE BRW-BB 6 & ORDER BACK BRW-KL 4`
  - donor moved X to Y: `ORDER BACK BRW-Y` (X not told)
  - borrow from the line's own location: `ORDER BACK`
  - rejected borrow: `CANCEL ALL` (unchanged)
- Resend uses the same function and rule. The OI Excel is unchanged.

## Code

- `_saved_line_parts(..., name_donors=True)` from `saved_line_remark` only. `_decision_words` and
  `_saved_decision_key` keep the unnamed words, so a donor move is still the same kind of decision
  (`record_saved_lines` donor-move branch unchanged).
- `handover_remark(..., donor=)`: a raised ORDER BACK row line names its `stock_location` when it
  differs from the LOCATION printed (`_handover_line`); used by Confirm row lines and resend.
- The planning board's "Confirm sends" preview (`saved_draft_remark`) goes through
  `saved_line_remark`, so it shows the same words.

## Tests

`tests/test_oi_saved_line_email.py` (OI-ORDERBACK-LOCATION section and the updated donor tests),
`tests/test_oi_orderback_location.py` (resend).

## Review notes

- The planning board's "Confirm sends" preview now names the donor too (UAC F3: the preview
  is the email's words). Where the board has no own location for a line, a borrow from that
  line's own location shows the donor in the preview but not in the email; that edge predates
  this lane.
- Reviewer S2 (not taken): a resent Order back BUY row whose `stock_location` went stale after
  the SO line's location moved would read `ORDER BACK <old location>`. Rows are restamped with
  the line (`ProjectSupplyService._restamp_stock_location`), and gating the donor on the
  "Order-back:" note instead would drop it from older borrow rows. Trigger to revisit: a real
  resend that names a stale location.
