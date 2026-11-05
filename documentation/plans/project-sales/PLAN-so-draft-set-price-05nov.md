# PLAN: SO draft set price (SO-DRAFT-SET-PRICE)

Status: built, in review (small fix track: under 300 lines, no migration, no auth/RBAC, no new ingest).

## Problem

`ProjectSODraftService._explosion_for` splits a quoted SET line into its frozen parts. The main
("driver") part was priced at the FULL set rate while its qty was also multiplied by its qty per
set. Set RM100 x 2 sets with a 2-per-set driver drafted `DRV 4 x 100.00 = 400.00` +
`OTH 2 x 0.00` against an accepted 200.00 (proved on main by lane AC-QTSO-CRM, PR #2173).

## Rule (owner, 5 Nov 2026, "ok a")

The driver is priced at set rate / its qty per set, so the split always adds up to the accepted
money. Unit prices stay whole cents. When the money does not divide evenly, the driver goes as two
rows of the same item: `(n-1) x rounded-down rate` + `1 x remainder` (RM100 x 1 set at 3 per set
-> `2 x 33.33 + 1 x 33.34`). Other parts stay at zero. 1 per set is unchanged.

## Build

- `sorento_crm_backend/app/services/set_driver_pricing.py`: `split_set_driver_price(set_rate,
  set_qty, driver_qty_per_set)`, the one shared function. AC-QTSO-CRM (#2173) reuses it.
- `project_so_draft_service.py`: the set snapshot path marks the driver with `set_rate`;
  `_draft_lines` prices it per slice through the shared function.

## Tests (`tests/test_so_draft_set_price.py`)

Shared function: 1 per set unchanged, 2 per set, 3 per set with remainder, the R6a example, an
exhaustive small matrix. Real `build()`: 1 per set, 2 per set (200.00), 3 per set rounding
(order total 100.00), mixed quotation with a plain line, rate-only set line, a PO whose
quotation version was never issued.

## Existing data

Published / amended / adopted orders are never rewritten by a build. Unsent drafts (draft,
blocked, ready) are deleted and rebuilt the next time the PO + schedule is built again; nothing
recomputes them on its own. Crew's dev check (20 Oct copy) found 0 affected rows; the owner runs
the read-only query in the PR body on prod. No data fix unless that finds rows.

## Known limit

`project_so_delta_service._lines_by_phase_product` keys lines by (area, sequence, product), so when
the driver goes as two rows of the same item an amendment's qty delta lands on one of them. Only
the remainder-cents case produces two rows; total qty stays correct.
