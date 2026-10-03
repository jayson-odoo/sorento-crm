# UAC - WA-CONCISE: WhatsApp replies, one fact per line

Plan: `PLAN-wa-concise.md`. Card v3: `documentation/mockups/wa-concise/index.html`.
Every string below is exact (WhatsApp `*bold*`, `_italic_`). `\n` = newline. No `·` anywhere.

## Line form (all ACs)

A product or order block is a bold heading line, then one fact per line `Label: value`
(label NOT bold), no blank line inside a block, one blank line between blocks. A reply with more
than one block numbers them `1. *X*`, `2. *Y*`; a reply with exactly one block has no number.
Flag lines (`⚠️  *(PRODUCT DISCONTINUED)*`, `🚩  *(PENDING ALLOCATION)*`, ...) stay, directly
under the block's last fact line.

## S1 Stock (crm_inventory_stock_balance_list)

- AC-1 Compact, one location: `*SRTWT5844-GM*\nBRW: 24 (O/S 10)` (no Total line; the
  location's granted value `24 (O/S: 10)` renders `24 (O/S 10)`). Ungranted: `BRW: 24`.
- AC-2 Compact, several locations: `3. *SRTSWT3001*\nTotal: 136\nBRW: 28\nMWH: 108`. With O/S
  granted the Total carries it: `Total: 136 (O/S 5)`.
- AC-3 Zero locations print as today: `4. *SRTSWT3001-GM*\nBRW: 0`. A compact entry with no
  location lines at all: `*X*\nStock: 0` (Stock = its total).
- AC-4 Detailed rows group per product in first-seen order; location label = system location
  code; `Outstanding` becomes ` (O/S n)` on its location line; `Total: N` (sum on hand) only
  when the product has more than one location AND one company. Two or more companies in the
  reply: the company name leads each location line and no Total:
  `*SRT6542-DIY*\nSorento BRW: 0 (O/S 233)\nMocha MOCHA-WH: 1`.
- AC-5 Openers removed when at least one block prints: "Stock details found for the requested
  products.", "Stock summary for the requested products.", "Here are the orders I found.",
  "Here are the delivered orders I found.", "Here are the matching products.". With zero
  blocks the existing text is unchanged.
- AC-6 Footer `_Updated 11/09/2026 17:26_` (was `_Data last updated: 11/09/2026 17:26:05_`)
  wherever the old footer printed; `turn/compose.py:451` and `answer.py:1564` find the new one
  (extras still slot above it; promo re-intro still keeps it).
- AC-7 Dealer availability replies (`stock_availability`) are byte-identical to main.

## S2 Cross-domain (incoming ask, nothing incoming)

- AC-8 Stock exists: whole reply
  `*SRTWT5844-GM*\nIncoming: none\nBRW: 24 (O/S 10)\n\nWould you like me to escalate to purchasing team?`
  No "Here's what you want", no "But no incoming matched these.", no "No incoming for X.", no
  "But here are the stock details for the requested products:".
- AC-9 All zero, nothing on order:
  `*SRTWT5844-BL*\nIncoming: none\nStock: 0\nPO: none\n\nWould you like me to escalate to purchasing team?`
  (a zero row with any non-zero O/S keeps its location line instead of `Stock: 0`).
- AC-10 No stock row at all, nothing on order: `*X*\nIncoming: none\nStock: none\nPO: none`.
- AC-11 PO placed: `PO: placed` then today's PO/SPO lines for that code, under the block.
- AC-12 Mixed (one code has incoming, one has not): incoming block(s) first, then the miss
  block, numbering continues:
  `1. *SRTWB1543*\nIncoming: 49\nETA: 2026-09-09\nContainer: IAAU1907074\nAllocation: BRW 35, BRW-BB 4, BRW-SMC 10\n\n2. *SRTWB1543-BL*\nIncoming: none\nBRW: 20\n\nWould you like me to escalate to purchasing team?`
- AC-13 Mirror (stock ask, stock 0, incoming exists): `*X*\nStock: 0\nIncoming: 49\nETA: ...`.
- AC-14 The escalation phrase and its quick replies are unchanged (LOCKED, tail/compose.py:96).
  Staff (no offer) get the same blocks without it.
- AC-15 A company searched but empty keeps `*Mocha:* no stock records for X.`

## S3 Incoming and order rows

- AC-16 Incoming rows: heading = product code; `Incoming Quantity` -> `Incoming`,
  `Estimated Arrival Date`/`ETA` -> `ETA`, `Container`/`Shipment Container` -> `Container`,
  `Warehouse Allocations` `BRW (35), BRW-BB (4)` -> `Allocation: BRW 35, BRW-BB 4` (warehouse
  alone when the quantity is withheld); other fields keep their label, unbolded. Values unchanged.
- AC-17 Order rows: heading = order number; `Status` first; `Actual Delivery Date` ->
  `Delivery Date`, `Pickup Time` -> `Pickup`, `Lorry Plate` -> `Lorry`; others keep label order.
  Example: `*SMC202609-0055*\nStatus: Picked Up / In Transit\nCustomer: CUSTOMER A (PROJECT-CASH)\nOrder Date: 08/09/2026\nDelivery Date: 09/09/2026\nPickup: 19:46:00\nTransporter: GLORY MOTION\nDriver: DRIVER B\nLorry: PLATE-1\nWarehouse: BRW\nProducts: SRTKS7547-NEW (1), TPE-9201 (1), SRTKT71SS (1), TRANSPORT (1)\n\n_Updated 10/09/2026 17:36_`
- AC-18 One named order whose number prints in the reply: no `Customer: all customers /
  Product: all products / Order: X / Dates: all dates` header. Broad searches and misses keep it.

## S4 Product list

- AC-19 `List Price` and `Dimensions` lines print only when the ask names price or dimensions
  (`requested_attributes` matched via `_names_a_base_property`); when asked and empty they
  still read `Not defined`. Not asked: neither line.

## Constraints

- AC-20 Values are never translated or reformatted except: O/S `(O/S: n)` -> `(O/S n)`,
  allocation `BRW (35)` -> `BRW 35`, footer drops seconds.
- AC-21 No `·`, no en/em dash in any changed reply text.
