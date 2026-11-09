# PLAN: Detect an SO line location change (SPLIT-SHEET-LOCATION)

Status: built, owner change request of 9 Nov (LOCATION / NEW LOCATION) in review (PR #2221). UAC: `split-sheet-location-acceptance-criteria.md`. Size M, one lane. One data migration: `oihr_0012_new_location` (the handover email template), added for the 9 Nov ruling; no schema change.

## Journey

Owner, 6 Nov: the Fulfilment Planning board shows SO429664 line SRTWT8239-GM at "BRW-BB" (its
AutoCount line location), but "Confirm SO429664" step 1 "Review split" shows "BRW". Rescope
(owner, 6 Nov ~16:15): this is a LOCATION CHANGE on the SO line that the system must detect the
same way it detects a qty, delivery date or item code change. Do not just switch the sheet.

## Findings (origin/main)

- `outstanding_diff._classify_identity` compared item, qty and date on an id-paired line, never
  location, so an ESB push that only moves the warehouse read `unchanged` and `build_batch`
  dropped it.
- `projects.sales_order_lines.stock_location` is set to the core warehouse at adoption and at
  every supply Confirm (`_restamp_stock_location`), or to what CS typed on the SO draft: it is
  the location the line was last planned at.
- The split sheet (`LineSplitService.line_facts`) preferred `stock_location`, so it showed the
  old planned location while the board showed the current AutoCount one.
- A re-Confirm of a moved Buy line sent a bare "ORDER" at the new location (reads as a fresh
  order).

## Owner answers (7 Nov ~11:30)

1. No backfill: only future AutoCount pushes are detected.
2. One row: a move riding with a qty / date change keeps today's kind and carries the location in
   from/to.
3. The Confirm email just states the move, "NEW LOCATION (was BRW)"; OI rows and links stay as
   they are, no cancel + reorder. Purchasing decides.
4. Any location change counts (no pool logic).
5. One lane / PR, no migration.

## Rule as built

1. Diff: `_classify_identity` returns `location_changed` for a location-only move on a line_id
   pair (ESB ingest, manual SO edit, cancel ingest). The id-less book upload is unchanged
   (location is in its group key).
2. Row: `_map_kind` -> `location_changed`; `_from_to` carries `location` on both sides whenever
   it moved on a line still open, any kind. A replace-in-place row keeps the planned location as
   its "from" even when the row it replaces was not a move (`_carry_location`); a move back to
   the planned location with nothing else changed retires the row with no replacement.
   `change_text` reads "Location A -> B".
3. Board: the change lightbox prints a Location Was/Now row; the history sheet labels the kind
   "Location changed". The row un-decides the line like any other kind, so CS re-confirms.
4. Purchasing: only via the board Confirm. A saved line whose snapshot location moved is told
   once with REMARK "NEW LOCATION (was <old>)" (alone, or after the qty /
   date words); LOCATION / NEW LOCATION print old / new (9 Nov ruling below). A line with acting splits says it once, on its
   first plan row (`_queue_plan_rows`). Lines purchasing holds nothing for (Use own
   location, Use BRW, incoming) stay out, as today (OI-EMAIL-PURCHASING-FOCUS).
5. Review split: LOCATION is the core warehouse (what the board reads), `stock_location` only as
   the fallback. The sits-on "same item and location" check compares that location.

## Owner change request (9 Nov 2026, ~16:40)

"When I confirm, is it supposed to show the Location and New Location column also in preview, email and
attachment?" Ruling, mirroring QTY | NEW QTY and DELIVERY | NEW DATE: in the Confirm Review split, the purchasing
email table and its Excel attachment, LOCATION prints the line's previous location and NEW LOCATION, right after it,
the new one, filled only on a moved line (blank otherwise), the column present only when some line moved. The
REMARK `NEW LOCATION (was X)` stays. At 375px both columns show (LOCATION used to be desktop-only).

As built: a moved email line carries `was.location` (as a cut carries `was.qty`); the stored email template gains
the column through `oihr_0012_new_location` (in-place edit guarded on `oihr_0011`'s document, with a downgrade);
`handover_xlsx` prints LOCATION / NEW LOCATION; the split read returns `was_location` off the same change NEW QTY
reads (pending, else last applied); `LineSplitSheet` adds the New location column and shows Location on a phone.

## Tests

`tests/scm/test_so_line_location_change.py` (diff, kind, from/to, refresh, history phrase),
`tests/test_so_line_location_change_email.py` (Confirm email, OI rows untouched, split sheet),
`tests/scm/test_planning_change_batch_kind_parity.py` (build_batch row + board feed),
`boardChangeAnnotations.test.ts` (annotation + changed fields).
