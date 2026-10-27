# UAC: BORROW-NO-HOLD - a Borrow decision is a plan, not a stock hold

Plan: `PLAN-borrow-no-hold-28oct.md`. Card: `CARD-borrow-no-hold-28oct.md`.
Status: agreed. Owner answers 28 Oct ~00:25: (a) on all (Q1, Q2, Q2b, Q3, Q4, Q5).

"Borrow" below means a confirmed `so_line_allocations` row with `source_type` `other_location` or
`other_project` on an ACTIVE decision (or a NULL decision). A step-3 supply Borrow (placement link) is not
one (Q2b).

## Stock Debt

- **AC-BNH-1 (date order).** A Borrow is a route, not a pin: on a bin with 36, an undecided line due +10d
  that may draw the bin gets 36 covered, and the later borrowing line (due +60d) reads short 36. Today: the
  borrower `pinned` 36, the earlier line short.
- **AC-BNH-2 (borrower first in time).** When the borrowing line is the earlier need it still reads covered
  from the bin its Borrow names (SO402757 shape: 42 + 42 + 16 on one line, three donors due later), and no
  row reads `pinned`.
- **AC-BNH-3 (cross-group reach kept).** A Borrow at a bin outside the borrowing line's own group still
  lets that line draw the bin at its own date (route), and an undecided line of the borrower's group still
  cannot draw it.
- **AC-BNH-4 (site pool).** A Borrow at a site pool (BRW) draws the pool at the line's date; a dealer line
  on the pool due first is served first.
- **AC-BNH-5 (unchanged binders).** OI placements on SPO / PO (including a step-3 supply Borrow's link),
  goods landed for the line's own purchase, and PO / SPO S/O pins still bind first at any date.

## Free stock and confirm

- **AC-BNH-6.** With a Borrow present: `free_stock_by_location` = on hand less AutoCount reserved;
  `held_stock_by_location` = 0; `holds_at_locations` lists nothing for it. Same on the board's free / held
  strip, location stock and the Allocation panel.
- **AC-BNH-7 (confirm keeps working).** Confirming a Borrow writes the same allocation rows, transfer
  proposal and buy-back `ORDER_BACK` Order Inquiry row as today. A second order may confirm a Reserve or a
  location Borrow on the same stock without being recorded short because of the first Borrow. One confirm
  still cannot give the same pile twice.
- **AC-BNH-8 (Q5 a).** A second group Borrow from the same donor LINE beyond its open qty less what other
  active Borrows already took from that line is still refused, as today.

## Board

- **AC-BNH-9 (Q3 a).** The donor's board cell still reads "71 lent to SO415472".

## Reorder runs (Q4 a)

- **AC-BNH-10.** A Borrow no longer lowers retail's planning supply (`retail_net`); the project half's own
  Buy is still lowered by Reserve and Borrow, as today.
