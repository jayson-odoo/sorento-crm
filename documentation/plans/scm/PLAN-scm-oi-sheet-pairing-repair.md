# PLAN: order inquiry sheet pairing repair - pair on AutoCount's own line ref

Status: IMPLEMENTED 14 Sep 2026, review pending. Owner go given ("we should do like 1 and
2 ... let's move forward"). Repairs the pairing #875 shipped. Lane
`fix/oi-sheet-pairing-direct-ref`.

UAC: `scm-oi-sheet-pairing-repair-acceptance-criteria.md`.

Parent plan: `PLAN-scm-oi-sheet-migration.md` (D1, D7, D9, D10 are amended here, nothing
else in it changes).

## 0. What was measured before writing this

Owner uploaded `JAN - DEC 2026 ORDERabc.xlsx` on prod on 14 Sep after #875 deployed. The
row SO347594 / CB2154-DIY / 87 linked to SPO-2025/11-0075 (from PO 202509-S0078) instead of
PO 202511-S0097, whose line 1241de6e carries `from_so_line_ref =
AED_SORENTO:41576559:41604391`, the exact SO line. The owner's own query is the right one:

```sql
select po.po_number from purchase_order_lines pol
join purchase_orders po on po.id = pol.purchase_order_id
where pol.from_so_line_ref = '<sales_order_lines.source_ref>';
```

The 3am 14 Sep prod backup is restored locally as `sorento_ai_automation_0913`. Replaying
the file through `_plan` + `_pair` against it reproduces prod exactly:

| sheet row | landed on | linked to | why |
| --- | --- | --- | --- |
| tab "JAN 26" row 113, cites 202511-S0097 | the 90-qty line (`...41599093`) | one S0097 line of qty 2 that belongs to SO 43525845, "2 of 87" | `_match_row` ranks by required date, never by which line the cited PO names; no claim on that line, so the sheet citation ran through `_purchase_side`, which picks the first same-item line of the PO |
| tab "JAN - APR 26" row 772, blank remark | the CANCELLED Aug-extract ghost line (`source_ref = '40'`) | SPO-2025/11-0075 lines 332 + 333 (37 + 50), "87 of 87" | only claim on the ghost is an Aug `po_history` Excel claim to 202509-S0078; `_BOOK_CLAIM_SOURCES` ranks it as book truth; D10 followed `from_po_number` to allocations that belong to other SOs |

Correct per AutoCount: line `...41604391` (87) <- PO 202511-S0097 line 1241de6e (87) <-
SPO-2026/01-0140 line 255 (87, `from_po_number = 202511-S0097`). Never considered.

**Why the claim path cannot carry this** (measured on the 3am copy):

| measure | count |
| --- | --- |
| PO lines whose `from_so_line_ref` resolves to a held SO line | 32,674 |
| ... with an `order_link_claim` naming that exact pairing | 4,277 |
| ... whose claim key `(so_number, po_number, item_code)` is already taken by another claim (Aug `po_history`, 33,235 rows, 21 Aug), so `claim_placed_on_po`'s fill-never-repoint swallowed the exact ref on the 9 Sep re-push | 28,397 |
| SPO allocations with a resolving `from_so_line_ref` / with a claim | 8,023 / 1,647 |
| AutoCount PO lines / with `from_so_line_ref` | 132,297 / 56,978 |
| AutoCount SPO allocations / with `from_so_line_ref` / with `from_po_number` | 69,197 / 10,627 / 64,034 |
| Aug-extract SO lines still present, cancelled, `source_ref` not `AED_SORENTO:` | 10,499 |
| claims pointing at them | 13,222 |

Whole-file replay on the 3am copy with the shipped code: 15,797 rows, 10,315 raised, 2,536
rows linked (1,343 "from book"), 607 partial, 1,949 no line.

The claim table is one row per `(so_number, po_number, item_code)` and never repoints. It
cannot represent "line 3 -> PO A, line 4 -> PO B" for two same-item lines, and it is
poisoned by the Aug Excel. The column AutoCount writes on the purchase side is exact and
already persisted. So the importer reads the column.

## 1. Owner rulings (14 Sep 2026)

| # | ruling | what it changes |
| --- | --- | --- |
| R1 | Pair directly: `purchase_order_lines.from_so_line_ref = sales_order_lines.source_ref`, and the `spo_allocations` twin, then `from_po_number` to the SPO. Claims are fallback, `po_history` is out. | D9 source 1 |
| R2 | Pick the SO line by the ref of the cited PO when several fit; a cancelled ghost line loses to any real line that fits. | D1 ranking |
| R3 | "what we need from the order inquiries tab is just the sales order, location, quantity, delivery date, product ... the remark doesn't really matter, differing remark is same also as long as other keys are the same" | D7 restatement key = SO + item + qty + date + location |

## 2. Design

All in `app/services/project_order_inquiry_import_service.py` unless said. No new table,
no new endpoint, no migration, no frontend change. Result contract (17 keys) unchanged;
`preview` and `apply` keep computing from the same `_plan` + `_pair`.

### 2.1 Restatement key (R3)

`_restates(row)` returns `(so_number, item_code, qty, delivery_date, location)`. The
remark, `po_numbers` and `order_back` leave the key (an ORDER BACK row has no delivery
date, so the date already tells it from a dated row). When `_plan` finds a duplicate it
extends the FIRST match's `cited` with any document numbers the restatement names that the
first did not (`_cited_from` order preserved), so a roll-up tab that carries the remark the
month tab left blank still lends its citation. The duplicate is still reported
`RESTATES_AN_INSTALMENT`, unchanged.

### 2.2 Line pick (R2)

`_plan` computes, once, `named_lines: Dict[str, set]` = for every cited document number
across the file, the set of `sales_order_lines.source_ref` values its purchase side names:

* a cited PO number: `purchase_order_lines.from_so_line_ref` of that PO's lines;
* a cited SPO number: `spo_allocations.from_so_line_ref` of its visible allocations, PLUS
  the `from_so_line_ref` of the PO lines of every distinct `from_po_number` those
  allocations carry (the chain read backwards, one extra query over PO numbers).

Two queries for the whole file (`_named_lines(db, numbers) -> Dict[str, set[str]]`).

`_rank_for(row, named)` key becomes:

1. `0` if `line.source_ref` is in the union of `named[n]` for the row's cited numbers, else `1`;
2. `0` if `line.line_status != "cancelled"`, else `1` (ghost last, never excluded: a lone
   cancelled line still matches, D1 kept);
3. the existing three: required date equals the sheet date, earliest required date (undated
   last), oldest `created_at`.

The "open before closed" term stays where it was (between 2 and 3). `_match_row` signature
gains `named: Dict[str, set]` (the row's cited numbers are on the row).

### 2.3 Pairing (R1)

`_pair` source order per raisable row, `need = row.qty`, capacity rule and `take()`
unchanged:

**Source 1, the ref.** `_ref_targets(db, core_lines)`: two queries over the set of core
line `source_ref` values (skip lines whose `source_ref` is NULL or empty):

* `spo_allocations` where `from_so_line_ref IN refs` and `product_id = line.product_id`,
  visible (`spo_supply.visible_line_clauses()`), ordered `spo_number, spo_line_number, id`;
* `purchase_order_lines` where `from_so_line_ref IN refs` and `product_id = line.product_id`,
  ordered `created_at, id`.

Per row: SPO refs first; then for each PO ref, the allocations `_chain_allocations` finds
for that PO line (D10, see below), then the PO line itself for the rest. Every take here is
`from_book=True` (counted under `links_from_autocount`, trigger "autocount linkage").

**D10 gains the finer key** (amended during implementation, 14 Sep, measured on the 3am prod
copy). `_chain_allocations` keyed only on `(from_po_number, product_id)`, and that is too
coarse: SPO-2026/01-0140 carries FIVE CB2154-DIY allocations from purchase order
202511-S0097 (300, 87, 1, 10, 2), one per sales order line, so the walk by number puts the
owner's 87 on the 300 that belongs to another line - the same class of error this plan
exists to repair, and it would have made section 4's own expected result unreachable. The
shipping order feed also states the exact purchase order LINE, in
`spo_allocations.from_po_line_ref`, quoting that line's `source_ref`. All 64,034 allocations
that name a source purchase order name its line too, and 64,026 of those refs resolve to a
purchase order line we hold, so the finer key is available wherever the coarser one is.
`_chain_allocations` therefore returns both maps, and `_pair` walks a purchase order line to
the allocations THAT LINE became, falling back to the whole document's allocations only when
the feed stated no line ref. Both sources use the same walk, so a claim-named purchase order
line is followed the same way.

**Source 2, claims the ingest wrote.** `_BOOK_CLAIM_SOURCES` becomes
`(SOURCE_AUTOCOUNT, SOURCE_PO_UPLOAD)`; `"po_history"` is removed. Loop unchanged
otherwise (SPO before PO, chain before PO line, `from_book=True`). A target already taken
by source 1 is skipped by `seen`.

**Source 3, the sheet's citation.** Unchanged, `from_book=False`.

`_target_facts` gains nothing: ref targets are fetched with their facts in the same query
shape it already uses (reuse it: collect ids from source 1, feed `_target_facts`).

### 2.4 Rollback of a wrong upload [script]

`scripts/rollback_oi_sheet_upload.py --file-name "<name as stamped>" [--apply]`, dry-run
by default. For rows whose `order_inquiry_rows.note` starts with
`"Migrated from order inquiry sheet <file-name>"` (the `_MIGRATION_STAMP` prefix, exact
string match on the prefix, company-agnostic):

1. delete their `order_inquiry_links`, and every `scm.order_link_claim` a deleted link's
   `claim_id` names (source `order_inquiry`, the link's own audit claim);
2. delete the rows;
3. delete `order_inquiries` headers left with zero rows (same rule
   `scripts/delete_empty_order_inquiries.py` applies; reuse its predicate if importable,
   else restate it in one query).

Header stamps (`demand_origin`, project label) and planning mirrors stay: harmless, and the
rerun rewrites them. Prints counts per step; `--apply` commits, otherwise rolls back. This
is what the owner runs on prod (per the prod one-off-script recipe) before re-uploading.

### 2.5 Nothing else

Not touched: `order_link_service` (the claim table stays as it is; its poisoning is a
separate cleanup, not this lane), the reader, the worklist readers, the route, the drawer,
the ingest.

## 3. Slices

| slice | scope | tests |
| --- | --- | --- |
| S1 | 2.1 + 2.2 + 2.3 in the importer | AC-R-1 to AC-R-12 |
| S2 | 2.4 rollback script | AC-R-13 to AC-R-16 |

One coder, one branch, one PR. Tester writes the red tests for both slices first.

## 4. Verification

* pytest: new `tests/test_oi_sheet_pairing_repair.py` (imports the seed helpers from
  `tests/test_project_order_inquiry_import_migration.py`), plus the existing 44 tests in
  that file stay green except the ones AC-R-9 and AC-R-12 name, which are rewritten to the
  new rule (listed in the UAC).
* Replay against `sorento_ai_automation_0913` with the owner's file (captain's
  `replay.py`): SO347594 / CB2154-DIY raises ONE row, on line `...41604391`, linked
  SPO-2026/01-0140 line 255 (`34e03b40`) for 87 of 87, `from_book` true, need left 0. The
  second sheet row for that pair is reported as a restatement. **Measured 14 Sep after the
  repair**: 15,797 rows, 8,270 raised, 5,727 rows linked (5,462 "from book"), 336 partial,
  854 no line - against the shipped code's 15,797 / 10,315 / 2,536 / 1,343 / 607 / 1,949.
  Fewer rows raised because the restatement key is looser (R3 drops the remark), and more
  than twice as many linked because the reference pairs what no claim states.
* No frontend change, so no browser pass; the drawer's preview keys are unchanged.

## 5. Owner steps after merge and deploy

1. Dry-run then `--apply` the rollback script on prod for the 14 Sep file name (the stamp
   is the upload's file name as the drawer sent it).
2. Re-upload `JAN - DEC 2026 ORDERabc.xlsx`.
3. Spot-check SO347594 / CB2154-DIY on Order Inquiries: one row, 87 of 87 on SPO-2026/01-0140.
