# PLAN - a received SPO must not keep covering an SO on Stock Debt (SPO-RECEIVED-PIN)

Status: built, PR #1388 open, 30 Sep 2026, small fix track (no migration, no auth change, backend only). UAC: `spo-received-pin-acceptance-criteria.md`. Hand test: `laneboard/scripts/1388.md`.
Domain: SCM, Stock Debt view and the shared supply assignment.

Owner (30 Sep, Stock debt drawer for SRTSS8710): "for the SPO that is received already, we
cannot take it already, cause when the SPO is received, it is on hand already, so if we still
link to the received SPO, it seems like there are more quantities than we should have."

## The problem, measured (origin/main 950785de2, `sorento_crm_backend/`)

- `StockDebtService._supply` (`app/services/scm/stock_debt_service.py:906`) reads on hand per
  bin, open SPO lines through `ProjectSupplyService.incoming_by_location` (`project_supply_service.py:9260`,
  the shared `spo_supply.open_incoming_clauses()` plus `allocated > received`), and open PO
  lines. A fully received or landed SPO line is correctly NOT supply.
- `StockDebtService._holds` (`:1143`) reads the placement links (`order_inquiry_links`) and
  filters only `OrderInquiryRow.state != cancelled` (`:1245`) and `visible_line_clauses()`
  (`:1249`, not retired-with-nothing-received). It never asks whether the SPO line is still
  incoming. A placement on a received SPO comes back as `Hold(kind=spo, supply_key=spo:<id>)`.
- `assign()` (`app/services/scm/supply_assignment.py:585-651`): a hold whose supply key is
  neither in `left` nor in `uncounted_by_key` falls to the stood-up branch (`:618-636`), which
  builds a synthetic SPO event dated `as_of` for the hold quantity, uncapped. That branch exists
  for AC-S2-1b (a hold naming supply outside this call's span). A received SPO is out of the
  span for a different reason: it is not supply any more.
- Net effect: the SO line keeps reading `pinned`, Covered by `SPO-...`, while the landed goods
  sit at the bin as on hand and cover a second line. One receipt counted twice.
- Timing note: the AutoCount stock balance ingest (`stock_balance_ingest_service.py`) can land on
  hand before the SPO line's `quantity_received` is written (`procurement_service.py:4537-4566`,
  `outstanding_import_service.py:1531-1552`). Between the two uploads the SPO is still open
  supply and the goods are also on hand. Not fixed here: it needs a signal the book does not
  carry yet, and the receipt write closes it on the next book upload.
- Precedent: `_landed_holds` (`stock_debt_service.py:1462`, #1362) already converts "goods that
  landed for this line on its own purchase" into an on-hand hold at the bin, capped by what the
  bin holds through `assign()`. Same shape, different trigger.

## The rule

**Once an SPO line is no longer incoming supply, a placement on it is an on-hand hold at the
SPO's warehouse, not an SPO hold.** "No longer incoming" is the negation of
`spo_supply.open_incoming_clauses()` plus the quantity test (`allocated <= received`), the one
rule every supply reader already uses. The converted hold is for
`min(placement qty, landed qty)`, where landed qty is `quantity_received` when the book has
written one and `allocated_quantity` when only the shipment's arrival says the goods are in.
`assign()` then caps it again at what the bin actually holds, so a bin that has since shipped
the goods pins nothing and the line reads short, which is the truth. The remainder of the
placement returns to the pool. **No stand-in SPO event is ever built for a received SPO.**

Where the floor is: a bin INSIDE the read's span with no on-hand event is a bin the read
looked at and found empty, so the converted hold is dropped (`_landed_holds` pins under the
same rule). A bin OUTSIDE the span (a site pool, an unflagged bin, another group under
`group=`) is one the read cannot see, so the hold is honoured the way every other out-of-span
hold is (AC-S2-1b). `_holds` takes the span and the supply events as two new keyword
arguments for this; its three direct test callers pass neither and get every hold listed.

A partially received, still-open SPO line is unchanged: the SPO hold pins off the netted
outstanding balance exactly as today, and the received part is free on hand.

The conversion lives in `_holds`, so both readers of this one assignment (the Stock Debt view
and the board / ladder through `assignments_for`) see the same picture.

## Slices

### S1 - red tests on the Stock Debt route (`tests/scm/test_stock_debt_routes.py`)

- AC-1: a fully received SPO placement reads pinned on on hand at the bin, the second line at
  the bin is short, the cell's Supply tab has no SPO row and foots with the bin's on hand.
- AC-2: a landed shipment (arrival date, nothing received yet) converts the same way.
- AC-3: a received SPO whose goods are gone from the bin pins nothing and the line reads short.
- AC-4: a partially received open SPO still pins as an SPO hold (regression guard).
- AC-6 (reviewer kill test): a line received in full by quantity alone, statuses still
  `pending` / `open`, converts too. The only branch the four above left unguarded.

### S2 - `_holds` conversion (`stock_debt_service.py`)

- The links query outer-joins `InboundShipment` and the SPO's `Warehouse` (direct joins, not
  aliases: the company-scope listener rewrites the un-aliased table name and an alias broke
  the query) and selects, beside the placement, `and_(*spo_supply.open_incoming_clauses())`
  as a `spo_incoming` label evaluated in SQL on the row (the way `spo_history_for_product`
  labels it), plus the line's `allocated_quantity`, `quantity_received`, `receipt_status`,
  `product_id`, `warehouse_id`, its warehouse code and the shipment's `actual_arrival_date`.
  No Python restatement of the three status tests and no new helper in `spo_supply.py`: the
  shared rule is reused unchanged.
- The quantity test (`allocated > received`) is applied in Python beside the arithmetic, as
  `open_incoming_clauses()`'s docstring asks of every reader. Incoming: SPO hold as today.
  Not incoming: on-hand hold as above, via the module helper `_landed_qty`.
- Also converted, because it follows from the rule rather than from "received": a placement
  on a line CLOSED with nothing received and no landed shipment now pins nothing (the
  document brought no stock anywhere); before, it stood up an SPO event and read `pinned`.

### S3 - hand-test script `laneboard/scripts/<PR>.md` (SRTSS8710 / SPO-2026/05-0001 case).

## Out of scope

- The stock-balance timing double count (noted above), and its mirror image: a shipment
  whose arrival date lands before the stock-balance upload puts the goods on hand pins
  `allocated` on the bin, so for that window the line is covered by whatever else sits free
  there. Totals stay right (nothing is counted twice); only the attribution is early.
- The converted hold names no order inquiry (an on-hand hold is a decision on stock, and
  `StockDebtAssignedFromOnHand` carries none). The `order_inquiry_links` row itself is
  untouched, so the Order Inquiry screens still show the placement on the received SPO.
- Any frontend change: the Covered by entry already prints `On hand <bin>` for an on-hand hold.
