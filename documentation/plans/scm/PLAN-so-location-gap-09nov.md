# PLAN: A location move made before #2221 is part of the next change (SO-LOCATION-GAP)

Status: Plan. Small fix track (S): no migration, no auth / RBAC change, no new ingest surface.
UAC: `so-location-gap-acceptance-criteria.md`.

## Journey

Owner, 9 Nov ~21:50, prod SO429664 (FULLSHUN BATH CONCEPT, SRTWT8239-GM, qty 2). The 06/11 Confirm
email said LOCATION BRW. AutoCount then moved the line to BRW-BB, before #2221 (location change
detection) shipped. A date change 06/11 -> 13/11 is now pending. On the board:

- "What changed" lightbox: only Date was 06/11 now 13/11. No Location row.
- Confirm Review split: LOCATION BRW-BB, no NEW LOCATION column.
- Review split REMARK (the email dry run's words): "DELAY, NEW LOCATION (was BRW)".

The remark knows the old location; the change row and the columns do not.

## Findings (origin/main e81cc34f36)

Two different references for "where the line was":

1. Change row (lightbox, Review split columns, history phrase) compares the two sides of the
   AutoCount DIFF. `planning_change_service._from_to` (`app/services/planning_change_service.py:822`)
   carries `location` only when `c.before.location != c.after.location` in that push. The move
   to BRW-BB happened in an earlier push, classified `unchanged` before #2221 and dropped, so this
   push's diff reads BRW-BB on both sides: no location in `from_json` / `to_json`.
   - Lightbox: FE `boardChangeAnnotations.ts:431` reads `row.from.location` / `row.to.location`.
   - Review split: `LineFacts.was_location` (`app/services/project_line_split_service.py:296`) reads
     the pending change's `from.location`; LOCATION is the core warehouse (`:829`), so BRW-BB with
     no NEW LOCATION.
2. Email (and so the Review split REMARK, which prints the dry run's words) compares the line's
   last CONFIRMED snapshot with the one this Confirm writes:
   `project_order_inquiry_service._location_moved_from(before, now)` (`:976`), read in
   `_queue_saved_line` (`:5689`), which also sets `was.location` (LOCATION / NEW LOCATION in the
   email table and its Excel). A first Confirm compares the live ORDER rows' location instead
   (`held_order_locations`, `:988`).

So the email is right by construction; the change row misses any move its own diff did not see.

Dev copy `sorento_prod_1104`: 21 of 5039 confirmed lines sit at a location other than their
confirmed snapshot's; 3 pending change rows carry no location for such a line (query in the PR).
SO429664 itself is not in that copy (taken 4 Nov).

## Rule (brief, 9 Nov)

When a line gets a change row (it is being re-confirmed) and its location now differs from the
location of its last confirmed decision (else, with no decision, the one location its live ORDER
rows sit at), that move is part of the change: the row carries `from.location` = old,
`to.location` = new, whatever kind it is. Lightbox prints Location was / now, the Review split
LOCATION old / NEW LOCATION new, the email and its attachment both (already), and the OI row
follows the line at the Confirm exactly as for a detected move. Lines with no new change row are
not flagged (owner Q1, 7 Nov: no backfill).

## Change

One seam: `_build_row` (`planning_change_service.py:2271`), right after `_from_to(c)`. When the
diff carried no location and the line is still open, read the planned location:

- the active decision's snapshot `location` for the line (`ProjectSupplyService._snapshot` writes
  the core warehouse code there at every Confirm), else
- `held_order_locations(db, [line])` (the email's own first-Confirm reference).

If it differs from `c.after.location`, set both sides. Kind is unchanged (owner Q2, 7 Nov: one
row, the move rides with it). The replace-in-place path (`_carry_location`) already prefers the
older row's `from.location`, else this row's own: it keeps working unchanged.

Nothing else changes: the split read, lightbox, history phrase and email all already read the row
(or the snapshots) the way they should.

## Open

- Rows already pending before this ships (SO429664 on prod, 3 on the dev copy) keep their
  location-less `from` / `to` until rewritten. Asked crew: one-off repair or leave.

## Tests (red first)

`tests/test_so_location_gap.py`, the exact owner sequence: Buy confirmed at the old location (ORDER
raised there), core line moved with no change row, then a date change detected through
`build_batch`:

1. The pending row carries `from.location` old, `to.location` new, kind still the date kind.
2. Review split: `was_location` old, `location` new.
3. Board Confirm with that batch: one email line at the new location, REMARK says the date word and
   `NEW LOCATION (was old)`, `was.location` old; the Excel prints LOCATION old, NEW LOCATION new.
4. The ORDER row ends exactly as for a detected move (same test, detected path).
5. A sibling line moved the same way but with no change of its own gets no row (no backfill).
6. First-Confirm variant: no decision, ORDER rows at the old location, date change: row carries
   the move.
