# PLAN: product-grain plan buys confirmed project demand without a reorder level

Status: in progress (10 Sep 2026)
Issue: #794
Lane: `fix/product-grain-project-buy` (worktree `.claude/worktrees/product-grain-project-buy`)
UAC: `product-grain-project-buy-no-level-acceptance-criteria.md`

## Journey

Buyer opens the reorder plan. CSK2800-QT carries 914 units of confirmed unplaced Order Inquiry
Buy (Project column 914) and no reorder level (AutoCount master 0, no buyer override). Today the
row reads Suggested 0 / "Nothing" and the panel says "none set today". The buyer expects the
914 to be bought: CS already confirmed it, a missing level only says nothing about the RETAIL
top-up.

## Cause (measured in code, 10 Sep)

`app/services/scm/reorder_run_service.py::_emit_product`:

```python
if level is None:
    triggered, reason_label = False, None
recommended = float(agg["recommended_qty"]) if triggered else 0.0
project_need = min(sum(project_need over cells), recommended)   # min(914, 0) = 0
...
if level is None:
    recs.append(_build_rec(run_id, "needs_level", ..., order_qty=None, rounded=None))
```

AC-E05 (confirmed unplaced Project Buy bypasses the trigger) is honoured in `_emit_pool`
(`pool_unplannable` -> `if pool_project_need > 0 and not triggered: triggered = True`) and in
`_compute_cell`, not in `_emit_product`. Since the per-product basis is the only path a
`reorder_level` product takes (27 Aug), every no-level product with project demand suggests 0.

Surfaced on 10 Sep because the owner deleted the bulk-seeded manual-50 rows; a master level of 0
reads as unset ("0 is not a level").

## Not a data fix

Setting `products.reorder_level = 0` by query is a no-op (already 0 = unset). Inserting manual
level-0 rows recreates the 13 Aug seed problem (manual outranks master, the upload refuses to
overwrite manual, the needs-level signal disappears). Rejected.

## Change (one function)

In `_emit_product`, after `agg` and the level trigger:

- `pool_project_need = sum(c["project_need"] for c in cells)`.
- If `level is None` and `pool_project_need > 0`: `triggered = True`,
  `recommended = pool_project_need`, `reason_label = "project buy: N confirmed unplaced Buy"`,
  `rounded = eng.round_order_qty(recommended, moq, order_multiple)`, `split` as usual.
  (Same shape as the existing bypass in `_emit_pool` lines ~1607-1612.)
- If `level is not None` and NOT triggered but `pool_project_need > 0`: same bypass
  (`recommended = pool_project_need`). Today the level path nets project demand inside `net`,
  so a level-set product with stock above level plus project demand already triggers on the
  net; the tester checks this stays byte-identical and the bypass is a no-op there.
- Emit order: a triggered buy with a supplier emits `buy` (with the allocation) even when
  `level is None`; the `needs_level` row is emitted ONLY when `level is None` and nothing was
  bought. `exception` when triggered and no supplier, as today.
- `project_need = min(sum, recommended)` and `retail_need` remain; with the bypass
  `retail_need` is 0 for a no-level product.
- The recommendation's `inputs.needs_level` stays True on the buy row (level still unset), so
  the panel still shows "Set AutoCount level to N".

No FE change: the sheet reads `suggested_qty` / `project_buy_qty` off the summary row.

## Tests (tester writes first, `tests/scm/test_reorder_per_product.py`)

1. No level anywhere + 914 confirmed unplaced Buy (seed via `_confirmed_leg` pattern from
   `tests/scm/test_channel_read_model.py`) + linked supplier -> one `buy` row, `rounded_qty`
   914, `triggered_reason` starts "project buy", `inputs.project_need` 914,
   `inputs.needs_level` True; summary row `suggested_qty` 914, `project_buy_qty` 914,
   `retail_replenishment_qty` 0. No `needs_level` row for the product.
2. No level + retail-only open SO demand -> still exactly one `needs_level` row, no buy
   (unchanged; existing `test_a_product_with_no_level_anywhere_is_named_not_guessed_at`
   stays green).
3. No level + confirmed Buy + MOQ 100 -> `rounded_qty` 1000 (914 rounded up by MOQ/multiple
   rules already in `eng.round_order_qty`).
4. No level + confirmed Buy + no supplier -> `exception` row, `inputs.project_need` 914,
   summary `suggested_qty` 914 (mirrors `test_confirmed_project_buy_survives_a_location_with_no_supplier`).
5. Level 500, on hand 600, confirmed Buy 50 -> byte-identical to today. `net` already
   subtracts committed (project included): net 550 >= 500, no trigger, no buy, the bypass
   must NOT fire on a level-set product. Read the file's existing net arithmetic first.
