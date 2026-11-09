# PLAN: A location move made before #2221 is part of the next change (SO-LOCATION-GAP)

Status: built, in review. Small fix track (S): no migration, no auth / RBAC change, no new ingest surface.
Owner ruling 9 Nov ~22:05: option (a), write-time fix plus a one-off repair script.
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

## Review round 1 (lane reviewer, 9 Nov)

- The planned location is THE reference, also when the push carries a move of its own: a line
  confirmed at A, moved to X before detection, then pushed X -> Y reads A -> Y (row, Review split,
  email "was A"). The replace-in-place path re-applies it after `_carry_location`, since an older
  row may name a stop in between.
- A fresh row whose push only takes the line back where it was planned is not raised (nothing
  left for CS to decide), as a replacement that nets to nothing already retires
  (`_nets_to_nothing`). With a date change too, the row carries only the date.
- The repair touches only rows with no location on either side (the gap the owner named), and
  sets the company scope to every company explicitly (`set_company_scope(db, None)`).
- Kept: `confirmed_locations` reads `line_snapshots` beside `_frozen_by_line` rather than adding
  `location` to frozen entries, which carry-forward and board paths consume; it reads one key and
  says nothing about coverage.

## Rows already pending (owner ruling (a), 9 Nov ~22:05)

Rows written before this ships (SO429664 on prod; on the dev copy SO423675 line 400, SO427115
line 96, SO427803 line 16) keep location-less `from` / `to`. `scripts/repair_pending_change_location.py`
gives each PENDING row what a row written now carries, through the same
`carry_planned_location`: dry run by default (prints SO / line / item / kind / old -> new / row
id), `--apply` writes `from_json.location` / `to_json.location` only; a repaired row carries a
location, so a re-run finds nothing. Prod, after the release that carries it (server A):

    cd /opt/sorento-crm2
    be=$(docker compose ps --status running --services | grep -E '^backend_(blue|green)$' | head -1)
    docker compose exec -T "$be" python scripts/repair_pending_change_location.py
    docker compose exec -T "$be" python scripts/repair_pending_change_location.py --apply

## Dev repro (sorento_prod_1104, rolled back)

SO422453 line 16 SRTWT165-QT: confirmed at BRW-AM (Buy 11, ORDER raised at BRW-AM), AutoCount
has it at BRW-BB, no change row. A date push +7 days at BRW-BB on both sides:

- main: row `delayed`, from/to location None; Review split LOCATION BRW-BB, no NEW LOCATION.
- fix: row `delayed`, from BRW-AM to BRW-BB; Review split LOCATION BRW-AM, NEW LOCATION BRW-BB.

Repair dry run on the same copy lists exactly the 3 pending rows above.

## Tests (red first)

Also `tests/test_repair_pending_change_location.py`: dry run prints and writes nothing, apply
writes what the lightbox and Review split read, re-run is a no-op, applied rows and unmoved lines
are left alone, an undecided line reads its ORDER rows' location.


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
