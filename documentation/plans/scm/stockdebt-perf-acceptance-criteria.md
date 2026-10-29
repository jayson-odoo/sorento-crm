# UAC: STOCKDEBT-PERF

Plan: `PLAN-stockdebt-perf-27oct.md`. Behaviour must not change: every number the board, the
export and a snapshot show stays identical.

## PR1: compute only products that can owe (A) + timing line (E)

- AC-SDP-1: With `only_debt=true` and `projected=false`, the board walks (`assign()`) only
  products that have at least one open sales-order line in the demand span (the same rule as
  `_demand`: `_demand_span`, SO status open, `is_open_demand()`, `is_transferable_order()`).
  A product with only stock, only an open PO line or only an open SPO allocation at the span is
  never walked.
- AC-SDP-2: The per-product reads behind the walk (supply, demand, holds, lead times, stand-in
  floors) and the reads after it (last supplier, aux columns) are not asked about a product
  AC-SDP-1 skips.
- AC-SDP-3: With `only_debt=false`, or `projected=true`, the products walked and listed are
  exactly today's (every candidate).
- AC-SDP-4: For every filter combination the board's rows (every field), `months`, `totals`,
  `suppliers`, `sheet_counts` and pagination total are identical to today's, and a saved
  snapshot and the export carry the same rows and numbers.
- AC-SDP-5: Each board build writes ONE INFO log line starting `stock_debt.board` that carries:
  candidates (products read), walked, rows, and milliseconds for the products read, the
  assignment, and the total. No product ids, codes or names in the line.
- AC-SDP-6 (lead, not CI): side-by-side harness on sorento_prod_1020 read-only, base sha vs
  lane sha, full board under the filter matrix: zero differences; warm median and p95 reported
  in the PR (counts only, no names: public repo).

## PR2: walk each product once (B), branch crew/stockdebt-perf-b stacked on #1901

- AC-SDP-B1: In one board build, `assign()` runs for a product once per DISTINCT set of pinned
  holds it is walked with. A product whose pinned holds are the same in the base pass, the
  landed-holds pass and the book-SO pass is walked exactly once (today: up to three times,
  stock_debt_service.py held_by_line called twice, then the final walk).
- AC-SDP-B2: The pinned holds handed to `assign()` for a product are exactly the holds whose
  line is one of that product's demand lines, in the order they sit in the full holds list
  (today's order; pins share a stand-in in hold order).
- AC-SDP-B3: Holds are bucketed by product once per pass, not filtered from the full list once
  per product (perf, measured by the harness, not a CI assertion).
- AC-SDP-B4: Same equality bar as PR1: side-by-side harness, zero differences vs PR1's head.

## PR3: read ids as text on the board's heavy reads (D), branch crew/stockdebt-perf-c stacked on PR2

Measured on the dev copy (PR2 head, default view): 233k UUID cells fetched per request, each
built as a `uuid.UUID` by the driver and turned back into `str` by the model type
(`UUID(as_uuid=False)`, app/models/base.py:143). `_demand` 80k, goods_chain `_placements`
(three calls) 49k, `_supply` 20k, `_holds` 10k.

- AC-SDP-D1: During one default-view board build, the result columns of `_demand`, `_supply`,
  `_holds` and goods_chain `_placements` carry no `uuid`-typed column (ids come back as text).
- AC-SDP-D2: Every id the board and the drill emit is the same string as before (Postgres
  `uuid::text` and Python `str(UUID)` are both lowercase hyphenated); NULL stays None.
- AC-SDP-D3: Same equality bar (side-by-side, zero differences vs PR2's head); statement count
  unchanged.
- Later, after #1899 / #1897 merge: transferred allocations read once per request (its two
  callers are in #1899's hunks today).
