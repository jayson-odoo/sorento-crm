# UAC: Flexible multi-level Group by on the stock status table (STOCK-GROUPBY)

Plan: `PLAN-stock-groupby-18oct.md` (card v1 rules 1-15, crew answers Q1-Q5 all (a)). Mock:
`documentation/mockups/STOCK-GROUPBY/index.html` v1. Frontend only; the AutoCount read
(`GET /api/v1/inventory/stock-status`, `components/stock-status/stockStatus.types.ts`) is unchanged.

Paths under `sorento_crm_frontend/`. "The table" = `CellStockTable`
(`app/(protected)/project-sales/fulfilment-planning/components/CellStockTable.tsx`); "the read" = its `autoCount` input.

## Lines (what gets grouped)

- AC-1 The lines come from the read only: one S/O line per `sales_orders` row (its qty in SO qty), one PO line per
  `purchase_orders` row (PO qty), one SPO line per `spos` row (SPO qty), and one On hand line per `locations` row whose
  `on_hand` is not zero (On hand). Incoming PL (`incoming_pl`) is never a line.
- AC-2 A line's values: Location = the warehouse code of its `warehouse_id` (On hand: its location's code);
  Customer = `debtor_name`, else `debtor_code`; Project = `project_label` trimmed; Agent = `salesperson`;
  Supplier = `supplier_name`, else `supplier_code`; Type = `On hand` / `S/O` / `PO` / `SPO`.
- AC-3 A line with no value for a dimension (empty, whitespace or null, or a type that has no such field, e.g. a PO
  line under Customer) belongs to `No customer` / `No project` / `No agent` / `No supplier`.

## Grouping

- AC-4 Levels are an ordered list over Location, Customer, Project, Agent, Supplier, Type. Each level splits its
  parent's lines into groups; a group exists only if it holds at least one line.
- AC-5 Order: Location groups follow the table's own location order; Type groups go On hand, S/O, SPO, PO; every other
  dimension A to Z by name (case-insensitive), its `No ...` group last. Lines inside a group go by location (table
  order), then type (On hand, S/O, SPO, PO), then the read's own order (due / expected date).
- AC-6 A group row shows its name, its line count (`1 line` / `n lines`) and the sums of On hand, SO qty, SPO qty and
  PO qty over its lines, exact to the read's decimals (no float drift). Available, Available for Project and Taken are
  blank on every group row.
- AC-7 For any levels, the top-level groups' sums of On hand, SO qty, SPO qty and PO qty equal the read's totals and
  the table's Total row.

## The table

- AC-8 Default levels = Location. With Location alone the table is today's, unchanged: same rows, sets, subtotals,
  Total and Incoming PL row; a location row opens today's documents drill-down (`StockDocumentsPanel`).
- AC-9 Location first plus more levels: today's location rows, sets, subtotals and Total stay with today's figures; a
  location row's chevron opens its next-level group rows instead of the drill-down; a set subtotal row's chevron opens
  the next-level groups over every line of its set's locations.
- AC-10 Location not first: the body is the first level's groups; the first column's heading names the first level
  (e.g. `Customer`); no set subtotal rows; the Total row and the Incoming PL row stay with today's figures.
- AC-11 No levels at all (every dimension unticked): the body lists every line flat in AC-5 order; Total and
  Incoming PL stay.
- AC-12 The last level opens its lines. A line shows its type and document number; the number links as the
  drill-down does today (S/O to `/scm/sales-orders/{sales_order_id}`, PO to `/scm/purchase-orders/{purchase_order_id}`,
  SPO to `spoDetailHref(spo_number)`); an On hand line shows its location code. A muted second line lists the values
  not already a level (Location, Customer or Supplier, Project, Agent; each only when present) and `due <date>` (S/O)
  or `expected <date>` (PO, SPO). The quantity sits only in its own column.
- AC-13 Every group starts closed and has a chevron that opens and closes it. `Expand all` opens every group at every
  level (and, Location first, every location row into its groups); `Collapse all` closes them all.
- AC-14 Negative sums are signed and shown in today's negative (red) style.

## The menu

- AC-15 A bar above the table holds the chip, `Expand all`, `Collapse all` and a `Group by` button. The button opens a
  menu of six ticks in the order Location, Customer, Project, Agent, Supplier, Type; a ticked item shows its level
  number.
- AC-16 Clicking an unticked item adds it as the last level; clicking a ticked item removes it and the later levels
  move up. The chip reads `Group by` and the levels joined by ` > `; its x sets the levels back to Location. With
  Location alone the chip has no x. With no levels the chip reads `Group by: none`.
- AC-17 The bar shows only when the table has the read. Without it (Borrow dialog `BorrowAddDialog.tsx:251`, the
  quotation's second mount `QuotationStockChip.tsx:308`, or the read failed) there is no bar and today's table.

## Remembered choice

- AC-18 The levels are saved in this browser (localStorage key `cellStockTable.groupBy`) on every change, and every
  table with the read starts from the saved levels, so all four screens share one choice.
- AC-19 A missing, unreadable or invalid saved value (unknown dimension, duplicates, not a list) and a storage that
  throws all fall back to Location without an error on screen.

## The four screens

- AC-20 The Fulfilment Planning cell dialog's Stock tab (`BoardCellBreakdownDialog.tsx:1298`), the order inquiry line
  expand (`OrderInquiryStockGrid.tsx:146`), the project quotation's stock popover (`QuotationStockChip.tsx:242`) and
  the stand-alone Stock status page (`StockStatusPageClient.tsx:55`) each show the bar and group as above.
- AC-21 Fulfilment Planning dialog, grouped (levels other than Location alone): the search narrows the lines it shows
  (document number, customer or supplier, agent; case-insensitive) and opens the groups holding a match; group rows
  keep their counts and sums. A jump button (My line / donor / document) opens every group that holds a line of the
  target location, down to its lines.
- AC-22 At 375px the bar wraps above the table, the table scrolls sideways inside its own container as today, and the
  page has no sideways scroll.

## Regression

- AC-23 Every existing CellStockTable, StockDocumentsPanel, OrderInquiryStockGrid, QuotationStockChip,
  BoardCellBreakdownDialog, BorrowAddDialog and StockStatusPageClient test passes unchanged.
