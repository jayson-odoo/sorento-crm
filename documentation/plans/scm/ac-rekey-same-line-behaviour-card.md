# Behaviour card - AC-REKEY-SAME-LINE: an AutoCount re-keyed SO line is the SAME line

Lane AC-REKEY-SAME-LINE, 6 Nov 2026. Code: origin/main 2cc1b2c5. Plan: `PLAN-ac-rekey-same-line-06nov.md`.

**Owner decision, 6 Nov ~15:15: (a) AUTOMATIC**, with two additions now in K1 and K6: the delivery
date is part of the key, and the delivered guard. Q2 no match on a Seq change, Q3 accept, Q4 log
line + `rekeyed` count, Q5 SO only, all as recommended. Anything that does not pair takes the
ordinary removal path (which, per FP-EMAIL-ONE-TRIGGER Q1, waits on the board for CS Confirm).
Data: the cloud worker cannot reach `sorento_prod_1104` (sandbox rule: no shared DB), so every
data claim below is either from the lane brief or marked UNVERIFIED with the query crew can run.

## What happens today

`_sync_lines` (`sorento_crm_backend/app/services/document_ingest_service.py:1472`) keys existing SO
lines by `source_ref` only (`:1513-1527`), matches the push by that key (`:1569-1570`), creates a
fresh row for every unmatched incoming line (`:1660-1672`), and treats every `by_ref` row the push no
longer carries as REMOVED (`:1681-1724`) -> `retire_rows_for_removed_so_lines` (`:1756`,
`project_order_inquiry_service.py:6313`) retires its OI rows and queues the purchasing handover.
The new row then gets a project mirror line via `mirror_missing_lines` (`:1771-1782`) with no OI row.
Lane brief case (4 Nov): one SO line got a new DtlKey, nothing else changed: demand of 118 lost.

## After this lane

| AutoCount push | Today | After |
| --- | --- | --- |
| DtlKey X gone, DtlKey Y new, same SO, same Seq, same item | X cancelled + OI rows retired + handover queued; Y created, new mirror line, no OI row | X's core line is updated in place (`source_ref` -> Y, plus whatever else changed, through the ordinary matched-line update path `:1571-1656`). Same ids, mirror line, OI rows, links. No cancel, no retire, no email, no new line, no planning diff (the diff is keyed by row id, `:1261-1323`) |
| X gone, Y new, different item (PVC 3 -> PVC 5 swap) | removal + create | unchanged (a real replacement) |
| X gone, nothing new on that Seq+item | removal | unchanged (genuine removal; email gating is lane FP-EMAIL-ONE-TRIGGER) |

## Rules

- K1 Match key: same SO header (already implied, `_sync_lines` is per header) + same AutoCount
  `Seq` (`sales_order_lines.line_no`, `models/order.py:843`; payload `line_number`, `:1393-1396`) +
  same resolved `product_id` + same `qty_ordered` + same `unit_price` (both compared as the columns
  round them) + same `required_date` (owner, 6 Nov) + same warehouse (when the push names one; D22
  leaves it out otherwise, `:1352-1360`). Only a line whose old DtlKey is ABSENT from this push and whose new
  DtlKey matches NO existing row can pair. Both Seq values must be non-NULL.
- K2 Uniqueness: a pair is made only when exactly one leftover row and exactly one new incoming line
  share that (Seq, product). Anything ambiguous falls back to today's behaviour (never a guess).
- K3 Everything else (remark, description) is NOT part of the key: once paired, the row takes the
  push's values exactly as a same-key re-push would.
- K6 Delivered guard (owner, 6 Nov): pair only when the old row has `qty_delivered` 0, no DO line
  (`order_lines.sales_order_line_id`) and no stock transfer (`projects.stock_transfers.so_line_id`)
  points at it, and the new line arrives with `qty_delivered` 0. A new DtlKey is a new AutoCount
  row, so whatever was delivered stays on the old one; crew census: all 26 real pairs pass this.
- K4 Only sales orders. PO lines are out of scope (no evidence of PO re-keys in the brief).
- K5 The re-key path calls no email or notification code at all; it is a key rename before the
  normal matched loop. Sales-order-only, no migration, no new column.

## Real examples (crew census on the 4 Nov prod copy, read-only; identifiers kept off the branch)

1. SO "A" (the brief's case), 4 Nov: one line re-keyed, Seq + item + qty + price + location equal,
   new row created within 5 s of the old cancel. Its OI row (qty 118) was retired and one handover
   email queued. After: paired; the core line keeps its id and the OI row stays live.
2. SO "B", 29 Oct: 25 lines re-keyed in one re-save, every field but DtlKey equal. No OI rows, no
   email, but 25 cancelled + 25 new rows. After: 25 in-place updates.
3. Near misses, 91 old lines on four SOs (24 Sep, 3 Nov, and two more): same SO + item, same moment,
   but a DIFFERENT Seq or qty. They read as real restructures and must NOT pair. This is why the
   key below includes qty, price and location, not Seq + item alone.
4. Same SO as 1, 3 Nov: item swaps (one product for another): item differs, not paired, as today.

Census: 26 true pairs in total (1 + 25); 0 seen with Seq + item equal and only qty changed.

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

- Q1 Key fields: (a) SO + Seq + item only / (b) also qty, price and location equal (K1). Rec (b)
  (revised after the census): every true re-key had all of them equal, and the 91 near misses that
  must not pair differ in Seq or qty.
- Q2 Seq renumbered by AutoCount on re-save: (a) no match (stays a removal) / (b) fallback on item +
  qty + price when Seq differs. Rec (a): the census shows no true re-key with a changed Seq, and the
  different-Seq near misses are real restructures.
- Q3 Old key used later by a DO/PO: (a) accept (old key resolves to nothing) / (b) keep the old key as
  an alias (new column, migration). Rec (a): minimum change; revisit if the census shows DOs on old keys.
- Q4 Trace: SO lines are `__audit_skip__` (`models/order.py:759`), so no row audit exists.
  (a) a `logger.info` line naming SO, Seq, old and new DtlKey + a `rekeyed` count on the ingest
  verdict's line counts / (b) a dedicated audit event. Rec (a): no owner-visible surface needed.
- Q5 PO lines: (a) SO only / (b) same rule on PO lines. Rec (a): no PO evidence.
