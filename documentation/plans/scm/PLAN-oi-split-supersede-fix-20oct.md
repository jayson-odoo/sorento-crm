# PLAN: kept-split Confirm on all-raised unlinked rows sends one DELAY (OI-SPLIT-SUPERSEDE-FIX)

Status: PR #1803, reviewer READY round 1 (S1 product follow, S2 refile assertion, N1 folded in);
crew reduce case (Cancel split) added, reviewer round 2 next, then CI. Owner: ships on CI green +
reviewer READY + red/kill proof, no hand test. Track: small fix (server-only, no UI, no
migration, no auth change). Lead pattern: red test first, one fix, reviewer, touched tests only.

## Defect

In the code prod runs (#1749 and #1794). Found by OI-SPLIT-VIEW (#1799) review on the dev DB
(15 Oct prod copy, SO417636 480); prod's rows may since be linked or placed, so whether prod
was hit is what the read-only check in the PR answers. Confirming a
saved split edit on a line whose split rows are ALL raised and UNLINKED (no
`order_inquiry_links` rows) cancels every split row and raises one unsplit ORDER for the full
qty at the line date, then stamps the edited plan as applied. Purchasing receives CANCEL per row
plus a fresh ORDER instead of one DELAY on the moved row. The same netting hits a REDUCE on such
rows (crew, 20 Oct: 104 = 52 + 52 edited to 28 + 24 + "Cancel this qty" 52): both rows are
cancelled and raised again instead of cut in place with one CANCEL BALANCE.

## UAC

1. Given a line split into three raised, unlinked rows and a saved split edit that only moves one
   split's date, Confirm sends exactly one DELAY (the moved row), no CANCEL, no fresh ORDER.
2. The two untouched rows keep their qty and date; the moved row carries the new date.
3. The edited plan is recorded as applied (the board's "Confirm (N)" flag clears).
4. Holds on a session with `autoflush=False` (the production session factory).

## Fix

See the PR body for the cause analysis with file:line evidence.

1. A split line `_kept_split_needs` acts on whose live plan rows (two or more, none refused)
   already ask for the new plan's total is re-filed, its product follows AutoCount, and
   `_keep_split_rows` moves only the rows the edit changed; the netting is not run for it.
2. `db.flush()` before `_keep_split_rows`: the session does not autoflush, so a fresh row the
   netting added for the last line read was invisible to it.
