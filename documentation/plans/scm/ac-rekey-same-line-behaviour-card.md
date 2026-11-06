# Behaviour card - AC-REKEY-SAME-LINE: an AutoCount re-keyed SO line is the SAME line

Lane AC-REKEY-SAME-LINE, 6 Nov 2026. Code: origin/main 2cc1b2c5. Plan: `PLAN-ac-rekey-same-line-06nov.md`.
Data: the cloud worker cannot reach `sorento_prod_1104` (sandbox rule: no shared DB), so every
data claim below is either from the lane brief or marked UNVERIFIED with the query crew can run.

## What happens today

`_sync_lines` (`sorento_crm_backend/app/services/document_ingest_service.py:1472`) keys existing SO
lines by `source_ref` only (`:1513-1527`), matches the push by that key (`:1569-1570`), creates a
fresh row for every unmatched incoming line (`:1660-1672`), and treats every `by_ref` row the push no
longer carries as REMOVED (`:1681-1724`) -> `retire_rows_for_removed_so_lines` (`:1756`,
`project_order_inquiry_service.py:6313`) retires its OI rows and queues the purchasing handover.
The new row then gets a project mirror line via `mirror_missing_lines` (`:1771-1782`) with no OI row.
SO398322 Seq 2552: DtlKey 44806451 -> 46204553, nothing else changed: demand of 118 lost.

## After this lane

| AutoCount push | Today | After |
| --- | --- | --- |
| DtlKey X gone, DtlKey Y new, same SO, same Seq, same item | X cancelled + OI rows retired + handover queued; Y created, new mirror line, no OI row | X's core line is updated in place (`source_ref` -> Y, plus whatever else changed, through the ordinary matched-line update path `:1571-1656`). Same ids, mirror line, OI rows, links. No cancel, no retire, no email, no new line, no planning diff (the diff is keyed by row id, `:1261-1323`) |
| X gone, Y new, different item (PVC 3 -> PVC 5 swap) | removal + create | unchanged (a real replacement) |
| X gone, nothing new on that Seq+item | removal | unchanged (genuine removal; email gating is lane FP-EMAIL-ONE-TRIGGER) |

## Rules

- K1 Match key: same SO header (already implied, `_sync_lines` is per header) + same AutoCount
  `Seq` (`sales_order_lines.line_no`, `models/order.py:843`; payload `line_number`, `:1393-1396`) +
  same resolved `product_id`. Only a line whose old DtlKey is ABSENT from this push and whose new
  DtlKey matches NO existing row can pair. Both Seq values must be non-NULL.
- K2 Uniqueness: a pair is made only when exactly one leftover row and exactly one new incoming line
  share that (Seq, product). Anything ambiguous falls back to today's behaviour (never a guess).
- K3 Everything else (qty, price, location, delivery date, remark) is NOT part of the key: once paired,
  the row takes the push's values exactly as a same-key re-push would (qty change -> the existing
  qty-change paths run, as for any edit).
- K4 Only sales orders. PO lines are out of scope (no evidence of PO re-keys in the brief).
- K5 The re-key path calls no email or notification code at all; it is a key rename before the
  normal matched loop. Sales-order-only, no migration, no new column.

## Real examples

1. SO398322 Seq 2552 CB2805A-DIY 118 @ 19.35 BRW-BB, DtlKey 44806451 -> 46204553 (4 Nov 09:28):
   paired (Seq 2552 + CB2805A-DIY unique on both sides; the other four CB2805A-DIY lines are Seq
   544/1328/1624/2312 and keep their own DtlKeys). Core line fad57dc2 keeps its id; OI-2609-0149
   stays live at 118; no handover; no mirror line 8b6ca35f.
2. Same SO, 3 Nov PVC 3 -> PVC 5 swaps: item differs -> NOT paired -> removal + create as today.
   UNVERIFIED whether those swaps kept the same Seq; either way the item differs.
3-5. UNVERIFIED (no DB access from the sandbox). Census query for crew on `sorento_prod_1104`
   (re-keys that already happened leave a cancelled AutoCount line and a live one on the same SO,
   Seq and product):

```sql
SELECT so.so_number, o.line_no, p.code, o.source_ref AS old_ref, n.source_ref AS new_ref,
       o.qty_ordered AS old_qty, n.qty_ordered AS new_qty, o.updated_at, n.created_at
FROM sales_order_lines o
JOIN sales_order_lines n ON n.sales_order_id = o.sales_order_id AND n.line_no = o.line_no
     AND n.product_id = o.product_id AND n.id <> o.id AND n.created_at >= o.created_at
JOIN sales_orders so ON so.id = o.sales_order_id
JOIN products p ON p.id = o.product_id
WHERE o.source_system = 'autocount' AND o.line_status = 'cancelled' AND o.cancelled_at IS NULL
  AND n.line_status <> 'cancelled' AND so.status <> 'cancelled'
ORDER BY n.created_at DESC LIMIT 50;
```

   The same query with `n.line_no <> o.line_no` (and same product, same qty) shows whether
   AutoCount ever renumbers Seq on a re-save; if it does, K1 misses those and they stay removals.

## Edge cases

- Two candidates (same Seq + item twice on either side): K2 falls back, today's behaviour.
- Old line already cancelled (CS Transfer to Cancel SO, `cancelled_at` set): pairs, and stays
  cancelled through the existing guard (`:1612-1620`); better than a fresh open line.
- Partly delivered old line: `qty_delivered` comes from the push like any update; nothing lost
  because the row id (the allocations, picking and DO links hang off it) is kept.
- DO pulled against the OLD DtlKey after the re-key: DO line lookup is by DtlKey
  (`autocount_doc_ingest_service.py:917-924`), and also PO `from_so_line_ref` / stock-debt links by
  SO `source_ref` (`scm/stock_debt_po_link_service.py:500`, `scm/order_link_service.py:203`). After
  the re-key the old key resolves to nothing (today it resolves to the cancelled line). AutoCount
  should send the new key on any later DO/PO; UNVERIFIED. No alias column is added (Q3).
- A push where the new line's product fails to resolve (dropped, `:647-652`): not in `line_values`,
  so it cannot pair; its own old row is already protected only by ref, so the old row is removed as
  today. Rare; left.

## Questions (recommendation first)

- Q1 Key fields: (a) SO + Seq + item, everything else may change (K1/K3) / (b) also require qty,
  price and location equal. Rec (a): Seq + item already identifies the line uniquely (the 5
  CB2805A-DIY lines differ by Seq), and (b) turns "re-key plus a qty edit" back into the 118-loss bug.
- Q2 Seq renumbered by AutoCount on re-save: (a) out of scope, needs the census above first / (b) add
  a fallback on item + qty + price when Seq differs. Rec (a): the brief shows the item+qty+price key
  is ambiguous on this very SO; no structural key without Seq.
- Q3 Old key used later by a DO/PO: (a) accept (old key resolves to nothing) / (b) keep the old key as
  an alias (new column, migration). Rec (a): minimum change; revisit if the census shows DOs on old keys.
- Q4 Trace: SO lines are `__audit_skip__` (`models/order.py:759`), so no row audit exists.
  (a) a `logger.info` line naming SO, Seq, old and new DtlKey + a `rekeyed` count on the ingest
  verdict's line counts / (b) a dedicated audit event. Rec (a): no owner-visible surface needed.
- Q5 PO lines: (a) SO only / (b) same rule on PO lines. Rec (a): no PO evidence.
