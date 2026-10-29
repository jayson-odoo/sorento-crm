# PLAN: STOCKDEBT-PERF - make the Stock Debt board fast without changing a number

Status: Build. PR1 #1901 merged (7f8011bd35), PR2 #1902 merged (c55eb336d0), PR4 #1914 merged (944937efab, fix forward for #1897: PO-received read as one statement without parallel workers); PR3 #1906 (ids as text) in CI. Follow-up after release: transferred allocations read once per request; re-measure once the dev copy has main's schema. Owner approved A -> B -> C on 27 Oct; statement_timeout dropped.
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
E. Timing line: one INFO line per board build with per-stage ms and product counts, so prod
   slowness is visible by stage. The request total is already logged by
   `LoggingMiddleware` (app/middleware/logging_middleware.py:72-76). NO statement_timeout
   (owner, 27 Oct: a hard limit is a dead end on a slow day). A graceful safety net (frontend
   progress state, or last-good snapshot fallback) is a separate owner question later, not in
   these PRs.
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

## PR1 measured (27 Oct, sorento_prod_1020 read-only, without #1899's index)

- Side-by-side, 13 filter combos + 24 cell drills: every number equal. Only difference: the one
  product with an exact last-supplier tie now reads the same supplier in every view (today it
  read one supplier in 4 views and the other in 2).
- Alternating A/B, 3 x 10 requests: base median 3.82-4.64 s, lane 3.41-3.57 s; min 3.60 -> 3.22 s.
  Walks 5,966 -> 2,691 (1,769 + 922 held_by_line re-walks).
- What is left (lane, per site): `_po_lines_feeding` 1.26 s (gone with #1899's index),
  transferred_allocations x2 0.39 s, `_oi_placements` + `_po_received_by_product` 0.25 s,
  `_demand_aggregates` 0.11 s SQL but ~0.6 s Python over 18k rows; Python 175k rows -> Row
  objects, 208k UUIDs, walk 2,691 calls. PR2 (B) and PR3 (C) target these.

## PR order

1. A + E timing line (biggest gain, smallest diff). UAC: `stockdebt-perf-acceptance-criteria.md`. 2. B. 3. C. 4. D only if still short of
target. F only on its trigger.

## Decisions (crew relay, 27 Oct)

1. Order A -> B -> C, timing line in PR1; D and the cache only on their triggers.
2. Profiling + equality harness run READ-ONLY on sorento_prod_1020 (no full copies; session
   forced read-only by a connect listener, because the app's own `connect_args` options
   override PGOPTIONS, app/database.py:17-18).
3. No statement_timeout (owner reversed it).

## Step 0 (27 Oct, sorento_prod_1020 read-only, scope = one company)

| Company | Candidates | With open demand | Demand lines | Rows in debt |
|---|---|---|---|---|
| main (00000000) | 5,044 | 1,769 (35%) | 20,105 | 1,025 |
| second (38db4f20) | 667 | 20 | 45 | 11 |

The profile's 5,966 walks = 5,044 products + the held_by_line re-walks. A walks 1,769.

A is identical by construction: `_demand` filters (stock_debt_service.py:1548-1556) are the
candidate demand read's (:1019-1029) plus product and date clauses, so every product with
demand rows is in the demand set; with no demand, credit is never negative
(supply_assignment.py:853 `free = max(left, 0)`), debit and the TBA/undated/unlocated buckets
come only from demand lines (:1265, :866-869), so `_in_debt` is false. The snapshot reads
`assignments` only for listed rows (stock_debt_snapshot_service.py:98). Projected view is left
walking every candidate (projection moves reserve stock; not proven).
