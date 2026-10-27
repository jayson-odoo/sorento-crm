# PLAN: STOCKDEBT-PERF - make the Stock Debt board fast without changing a number

Status: Plan, waiting on owner (crew --ask filed 27 Oct). Track: small fix track per PR (each PR
under ~300 lines, no migration, no auth change); lane is LEAD pattern (tester + coder + reviewer
subagents). Page for the owner: `stockdebt-perf-27oct.html` beside this file.

## Journey

Owner, 27 Oct: "please look into how to make the stock debt faster and more efficient". Prod
timed out today (shm 64MB, then goods_chain row-IN seq scans); it now loads but slowly on a 4
core / 16 GB box where db + backend often sit above 80% CPU.

## Where the time goes (crew profile, local clone sorento_prod_1020, code 782a45162c + ix_spo_allocations_from_po_key)

`GET /api/v1/project-sales/stock-debt?page=1&limit=25&only_debt=true&book=all&projected=false`

| Run | Total | SQL | Python | Statements |
|---|---|---|---|---|
| with index, warm (p782.run1) | 3.38 s | 1.94 s | 1.44 s | 53 |
| with index, run 2 (p782.run2) | 4.24 s | 2.09 s | 2.16 s | 51 |
| no index (p782noidx.run2) | 6.81 s | 4.77 s | 2.03 s | 51 |

Root shape: `list()` builds the WHOLE board (`_board`, stock_debt_service.py:387) for all 5,966
candidate products, then slices 25 rows (stock_debt_service.py:373-374). Every page flip
recomputes everything.

Top SQL (p782.run2): transferred_allocations x2 0.365 s + 0.195 s (goods_chain.py:242, callers
stock_debt_service.py:1913 and goods_chain.py:788); _po_lines_feeding 0.243 s with index, 1.2 s
without (goods_chain.py:673, PR #1899); _demand_aggregates 0.218 s; _last_supplier_map 0.187 s
(row_number over every PO line, stock_debt_service.py:2603); _oi_placements 0.116 s (PR #1897
area); _po_rows 0.101 s; _demand 0.087 s.

Top Python (cProfile prof.run2, inflated about 2x by the profiler): walk x5,966 1.03 s cum
(stock_debt_service.py:1238), of which assign 0.75 s (supply_assignment.py:602) and walk's own
0.27 s, mostly `pinned = [hold for hold in all_holds if hold.line_key in line_keys]`
(stock_debt_service.py:1251), a scan of EVERY hold for EVERY product; held_by_line walks again
twice (stock_debt_service.py:1277, called at 1302 and 1312); 215k result rows -> Row objects
0.34 s; 245k UUID objects built and stringified 0.39 + 0.17 s.

## Options, ranked (gain / effort / risk)

A. Narrow to debt candidates before compute (only_debt=true, not projected). `_products`
   already reads the open-demand product set (stock_debt_service.py:1017-1029). With
   only_debt, a product with no open demand line cannot be in debt: `assign()` drops supply
   events with qty <= 0 (supply_assignment.py:631) and balance = credit - debit
   (supply_assignment.py:1274), debit coming only from demand. So feed `_assignments` only the
   demand set. Every per-product read and the walk shrink in proportion. Gain: largest
   (UNVERIFIED until step 0 measures demand products vs 5,966). Effort S. Risk low-medium:
   the invariant is proven by a unit test plus the equality harness.
B. Walk cost: index holds by line key once (removes the products x holds scan), walk each
   product once and reuse it for held_by_line. Gain ~0.2-0.4 s. Effort S. Risk low.
C. One transferred_allocations read per request instead of two, and the remaining SQL:
   `_last_supplier_map` as DISTINCT ON over an index, `_demand_aggregates`, `_po_rows`
   (EXPLAIN on the copy first; any index = migration, then L rules apply). Gain ~0.3-0.5 s.
   Effort S-M. Risk low.
D. Row -> object cost: select id columns as text and plain tuples on the hot reads, not ORM
   rows + UUID objects. Gain ~0.2-0.4 s, mostly absorbed by A. Effort M. Risk low.
E. Guard rails: `SET LOCAL statement_timeout` on the board request so a runaway query dies
   instead of eating the box, plus one INFO timing line per request (total, sql, statements,
   products) so prod p95 is read from logs without anyone touching prod. Effort S. Risk low.
   Frontend "took too long, retry" only if the owner asks (UI change).
F. Cache (parked). Per (company, scope, filters) board cache would make page flips free, but
   invalidation spans every write path (imports, GRN, Respond, links, holds) and a TTL shows
   stale numbers. Trigger to build it: A-E land and warm p95 is still above target.
   Materialised worker snapshot: rejected (stale by design, changes behaviour).

Already in flight, not duplicated: #1899 GOODSCHAIN-INDEX-QUERY (index + unnest join for
_po_lines_feeding), #1897 STOCKDEBT-SHM-QUERY (bounded _po_received_by_product). This lane
rebases on them.

## Target and measurement

- Target: default view warm p95 < 1.5 s, cold < 3 s, on sorento_prod_1020 locally; SQL
  statements <= 53 (no N+1 introduced).
- Method: crew's in-process harness (`prof_sd.py`, NOPROF) 10 runs per arm, median + p95, same
  DB, same day, base sha vs lane sha.
- Prod: the timing line from E, read by the owner from prod logs after a release. Crew never
  touches prod.

## Equality (numbers equal row for row)

- Harness script (dev only, under `scripts/`): for a filter matrix (default; only_debt=false;
  each book; a group; location include/exclude; date_from/date_to; supplier incl. `none`; query;
  projected=true) dump the FULL board as canonical JSON (every row, months, totals, suppliers,
  sheet_counts), plus `cell()` drills for a sample of cells and the export rows. Run at base sha
  and lane sha against the same read-only DB; the diff must be empty, exact floats. PR body
  carries counts only (public repo: no names).
- CI: red-first pytest per PR pinning the property (A: a stock-only product is never walked and
  its reads are not issued; B: walk count == products; C: statement count bound) plus the
  existing tests/scm stock debt suites unchanged and green.

## PR order

1. A + E timing line (biggest gain, smallest diff). 2. B. 3. C. 4. D only if still short of
target. F only on its trigger.

## Open questions (crew --ask)

1. Approve order A, B, C, E (D, F conditional)?
2. DB for profiling + equality harness: a lane throwaway copy of sorento_prod_1020, or read-only
   on sorento_prod_1020 itself?
3. statement_timeout value (recommend 20 s) and no frontend change?
