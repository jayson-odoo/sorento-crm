# Acceptance criteria: order inquiry sheet - one item cell naming several products

Companion to `PLAN-scm-oi-sheet-multi-product-cell.md`. Every criterion is verified by a
pytest on Postgres (`tests/_pg_fixture.py`, `blank_session`), seeding its own chain through
`tests/test_project_order_inquiry_import_migration.py`'s `World` / `sheet` / `book` / `world`.

## Journey

Same operator, same Upload button as `scm-oi-sheet-migration-acceptance-criteria.md`. The
one thing that changes for them: a sheet row whose ITEM CODE cell reads
`SRTWCX8608-RL + SRTWCY8608 + SRTWC8608-SC` raises three order inquiry rows, one per code,
each for the row's quantity, instead of landing whole in "No sales order line for this
item".

Fixture vocabulary: "member" = one code of a `+` cell; "cell quantity" = the row's QTY.

## Slice S1, the importer [BE]

Splitting (plan section 1)

* AC-M-1 Given an order with lines for products A, B and C (each qty_ordered 5) and a sheet
  row `A + B + C` qty 5, when applied, then three order inquiry rows are raised (one on each
  line), each with qty 5 and the row's delivery date, and the result reports `rows_raised`
  3 and `rows_line_not_found` 0.
* AC-M-2 Given lines A and B and a row `A+B` (no spaces) qty 2, when applied, then two rows
  are raised. Same for `A +B` and `A+ B`.
* AC-M-3 Given a product whose code is `FUR-GA30T+A66C` with a line on the order, and a
  sheet row with that exact cell, when applied, then ONE row is raised on that line and
  nothing is reported as `no_line_for_item` for `FUR-GA30T` or `A66C`.
* AC-M-4 Given lines A and B only and a row `A + B + Z` qty 1, when applied, then A and B
  raise, and `line_not_found` holds exactly one entry `{item_code: "Z", reason:
  "no_line_for_item", qty: 1}`.
* AC-M-5 Given a row `A + + B` (empty member) or `A + B +` (trailing plus), when applied,
  then exactly A and B raise and no empty-code entry appears anywhere in the result.
* AC-M-6 Given lines A and B and rows `A & B`, `A / B`, `A C/W B` (none a product code),
  when applied, then each is ONE `no_line_for_item` entry naming the whole cell (no split
  on any separator but `+`).

Downstream stays right (plan section 2)

* AC-M-7 Given a month tab and a roll-up tab both carrying `A + B` qty 3 on the same
  order, date and location, when applied, then two rows are raised (A once, B once), not
  four.
* AC-M-8 Given line A qty_ordered 5 and rows `A + B` qty 5 then `A` qty 1 (later in the
  same file), when applied, then the second row reports `qty_exceeds_ordered` (the member
  charged the ledger).
* AC-M-9 Given AC-M-1, when previewed and then applied, then `preview` and `apply` report
  the same `rows`, `rows_raised` and `rows_line_not_found`.
* AC-M-10 Given a two-tab book with 2 sheet rows of which one is `A + B + C`, when applied
  with an `on_total_rows` callback and an `ImportOutcome`, then the callback receives 4 and
  the result's `rows` is 4 (expanded count, matching what the outcome records).
* AC-M-11 Given a member row A with a purchase order line that names line A's ref, when
  applied, then the raised A row is linked to that PO line exactly as a plain `A` row
  would be (AC-R-1 unchanged for members).
* AC-M-12 Given an order not found (`SO-NOPE`) and a row `A + B`, when applied, then
  `sales_orders_not_found` names the order once and nothing is raised.

Evidence (plan section 4, not a pytest)

* AC-M-13 `preview` of `JAN - DEC 2026 ORDERabc.xlsx` on the 0907 copy, before and after:
  count of `+` item codes in `line_not_found` goes from 173 to the members with no line on
  their order; `rows_raised` increases by the matched members. Numbers recorded in the
  plan's Status line.
