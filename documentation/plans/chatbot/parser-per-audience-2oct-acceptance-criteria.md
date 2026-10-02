# UAC: parser prompt rendered per contact audience

Plan: `PLAN-parser-per-audience-2oct.md`. Status: draft, pending the owner's answers on #1429.
Tests run on Postgres only (`tests/_pg_fixture.py`).

- **AC-PA-1 Full render unchanged.**
  - Setup: setting `chatbot_parser_per_audience` on; a contact holding `purchase_orders.cost`,
    `purchase_orders.placed`, `sales_orders.sales_report` and `scm.low_stock_report`.
  - Expected: the rendered parser prompt is byte-identical to today's render of the same
    `production` version (markers removed, nothing else).
- **AC-PA-2 Setting off means no change.**
  - Setup: setting off; any contact, a dealer with no grants included.
  - Expected: the full render, byte-identical to AC-PA-1.
- **AC-PA-3 Dealer render carries no cost / PO / sales figure / low stock text.**
  - Setup: setting on; a contact with none of the four grants.
  - Expected: the render contains none of these (case-insensitive, word-bounded): `purchase_cost`,
    `check_po_cost`, `purchase cost`, `last purchase cost`, `purchase_order`, `check_po`,
    `purchase order`, `PO`, `sales_report`, `sales_analysis`, `top_selling`, `low_stock_report`,
    `LAST PURCHASE COST`, `SALES REPORT`, `SALES ANALYSIS`, `TOP SELLING`, `LOW STOCK REPORT`.
  - On the owner's prod text its token count is no more than 27,000 (o200k_base); measured
    26,666 before inline spans.
- **AC-PA-4 One gate per block.**
  - A contact holding only `sales_orders.sales_report` gets the sales blocks and no cost / PO /
    low stock text.
  - The same holds for each of the other three grants on its own.
- **AC-PA-5 Audience comes from grants, not access types.**
  - Two contacts with the same access type ("Sorento Dealer") and different grants get different
    renders.
  - Two contacts with different access types and the same grants get identical renders.
- **AC-PA-6 Same version stream.**
  - Moving the `production` label to another version changes every audience's render on the next
    turn after the cache TTL.
  - No second version or label is created per audience.
- **AC-PA-7 Backend still refuses (the security control).**
  - Setup: a dealer contact with no grants, and a parser output FORCED to the restricted asks.
  - `domain_hint purchase_cost` gets "Sorry, you are not allowed to access purchase cost", and
    no tool runs.
  - `order_status sales_report` / `sales_analysis` / `top_selling` gets "Sales report is not
    enabled for your account." (`engine.py:3936-3951`).
  - Low stock report: refused.
  - `domain_hint purchase_order`: refused outright if Q2 is approved. Otherwise the answer
    carries no restricted PO field.
- **AC-PA-8 Malformed tags never leak or crash.**
  - An unbalanced, nested or unknown tag renders the block KEPT, with markers removed, and a
    warning is logged.
  - The turn still parses.
- **AC-PA-9 Unresolved contact** (ambiguous workspace or no row): gets the render Q5 decides.
  The recommendation is the minimal one.
- **AC-PA-10 Console turn.** A staff console dry run as contact X renders X's audience, and the
  trace records the audience key (the sorted list of the grants held).
