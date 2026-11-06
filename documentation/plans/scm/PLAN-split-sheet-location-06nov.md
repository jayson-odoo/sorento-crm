# PLAN: Detect an SO line location change (SPLIT-SHEET-LOCATION)

Status: waiting on owner answers to the behaviour card (PR comment `crew-ask`). Size M, one lane,
no migration expected.

## Journey

Owner, 6 Nov: the Fulfilment Planning board shows SO429664 line SRTWT8239-GM at "BRW-BB" (its
AutoCount line location), but "Confirm SO429664" step 1 "Review split" shows "BRW". Rescope
(owner, 6 Nov ~16:15): this is a LOCATION CHANGE on the SO line that the system must detect the
same way it detects a qty, delivery date or item code change. Do not just switch the sheet.

## Findings (origin/main)

- `outstanding_diff._classify_identity` compares item, qty and date on an id-paired line, never
  location, so an ESB push that only moves the warehouse reads `unchanged` and `build_batch`
  drops it. The only trace is an `OrderInquiryConflict` row nobody can see (no FE).
- `projects.sales_order_lines.stock_location` is set to the core warehouse at adoption and at
  every supply Confirm (`_restamp_stock_location`), or to what CS typed on the SO draft: it is
  the location the line was last planned at.
- The split sheet (`LineSplitService.line_facts`) prefers `stock_location`, so it shows the old
  planned location while the board shows the current AutoCount one.

## Proposed rule (pending owner answers)

1. Diff: `_classify_identity` also compares location; a location-only move is a new kind
   `location_changed`; combined with another change it rides on that row.
2. Row: `from_json` / `to_json` carry `location` when it differed.
3. Board: cell reads changed, old -> new location. CS re-confirms.
4. Purchasing: only via the board Confirm. Applying restamps `stock_location` and live OI rows;
   handover email verb `CHANGE_LOCATION` ("NEW LOCATION").
5. Review split: current AutoCount location, old planned location marked when different.
6. Optional backfill for lines already moved (owner question 1).

## Tests

Red first, seeded SO429664-shaped data (planned BRW, AutoCount BRW-BB): diff classification,
`build_batch` row and from/to, board annotation, Confirm handover verb, split sheet location.
