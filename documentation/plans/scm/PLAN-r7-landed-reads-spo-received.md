# PLAN: R7 own-arrival credit reads what LANDED on the SPO, not what the PO transferred

Status: in review, PR open (24 Sep 2026); coder green (38 pass across the five s3 files), reviewer round 1 folded (B1 kill tests, S1 planning-engine sentence, S2 company equality on the batched join, N2 docstrings). Open ruling S3 below. Merge needs owner go. Track: small fix track, stretched - one seam, no migration, no auth change, but the R7 test fixture seeds the wrong document so four existing test files move with it. One coder writes tests + fix, one reviewer, no browser pass (no UI code changes; the refusal message is asserted in pytest). Lane `fix/r7-landed-reads-spo-received`, worktree `sorento_crm-r7-spo`. Follow-up to `PLAN-board-received-stock-own-arrival.md` (R7, PR #1092, merged as 2280975f9).

## The problem, measured (SO399639 line 58 / core line 2120, C-FHSS18, prod 24 Sep 2026)

Board Confirm refused with:

```
SO399639: 1 landed for this line on PO 202607-S0079; nothing to buy for it
Line 58, C-FHSS18: 1 landed for this line on PO 202607-S0079; nothing to buy for it
```

Prod rows behind it (owner ran `scratchpad/so399639-*.sql`, 24 Sep):

| Row | Value |
| --- | --- |
| `sales_order_lines` 2120 | `source_ref AED_SORENTO:44533747:44560139`, qty 7, delivered 0, open, required 2026-09-10, bin BRW-IB |
| `purchase_order_lines` on PO 202607-S0079 | `from_so_line_ref` = that ref, `source_ref AED_SORENTO:45346073:...`, qty_ordered 7, **qty_received 7**, updated 24 Sep 02:05 |
| `spo_allocations` SPO-2026/09-0091 line 403 | 7 pcs, BRW-IB, `quantity_received 0`, expected 2026-09-18, `from_po_number 202607-S0079`, `from_po_line_ref` = the PO line's `source_ref` |
| `stock` C-FHSS18 | BRW-IB 1, BRW-SMC 40 |

Nothing has physically landed. The PO line's `qty_received = 7` is the AutoCount TRANSFER of the
line onto the shipping order (owner, 24 Sep: "PO received 7 means it is converted to SPO, it
doesn't mean it is received"). R7 (`_own_arrival_credit_components`) reads
`purchase_order_lines.qty_received` as "landed", gets 7, caps it by on hand at BRW-IB (1) and
refuses the Buy the board itself proposed (the SPO is late against 2026-09-10, so the proposal
was Buy 7 - correct per the owner's ruling below).

Every PO in this business is received through an SPO (owner, 24 Sep: "all PO received via SPO for
order inquiries"). So `purchase_order_lines.qty_received` NEVER means landed; the physical
receipt is `spo_allocations.quantity_received`.

The SO372176 case that built R7 did not show this because there the PO lines and the SPO
allocations were BOTH fully received (parent plan, "The problem, measured", line 18), so the two
readings agreed.

## Rulings (owner, 24 Sep 2026)

- **R1** "Landed for this line" = `spo_allocations.quantity_received` on the SPO rows that carry
  the line's purchase-order line, resolved SO line -> PO line -> SPO row. PO `qty_received` is a
  transfer, never counted.
- **R2** A late own-SPO (arrival after the line's required date) still gets a Buy proposal ("buy
  is fine"). No change to `_group_water` / R32.
- **R3** The refusal names the SPO number (the document the goods landed on), not the PO.

## The chain in data (measured on the 0921 copy, 24 Sep)

`sales_order_lines.source_ref` == `purchase_order_lines.from_so_line_ref` (already how R7 finds
the PO line) and `purchase_order_lines.source_ref` == `spo_allocations.from_po_line_ref`
(817 of 817 open SPO rows with a ref resolve; `spo_allocations.po_line_id` is NULL on every one
of the 1,152 open rows, so it is not the key). Product and company filters stay exactly as R7
states them.

## The fix (one seam, two reads)

`app/services/project_supply_service.py`:

1. `_po_received_by_so_line_ref` (:2731) - the per-order read. Join
   `SPOAllocation` on `SPOAllocation.from_po_line_ref == PurchaseOrderLine.source_ref` (same
   product, same company filter as today), sum `SPOAllocation.quantity_received` per
   `from_so_line_ref`, and return the SPO's `spo_number` as the document. A PO line with no SPO
   row contributes zero. `qty_received` on the PO line is no longer read.
2. `_prefetch_own_arrival` (:2788) - the batched read of the same shape. Same join, same
   bucketing by (product, company).

Nothing else changes: `_own_arrival_credit_components`, the on-hand cap, tier 2's sibling spare
(`spare = received - min(received, sibling.qty_ordered)`, now off SPO received), the ledger,
`_check_line`'s refusal and `planning_change_service._refuse_buy_over_own_arrival` all read the
same tuple `(qty, document)` and keep working. The message template already says "on PO {x}";
change the noun to "on {x}" so an SPO number reads right (`:5517`, and the
`planning_change_service.py:2821` twin).

## Tests (pytest, Postgres, `tests/scm/`)

Fixture `tests/scm/_own_arrival_fixture.py` `po_line_bought_for` gains the SPO half: it writes the
PO line as today (a transfer, `qty_received = qty_ordered` to mirror what the book import
stamps) AND an `SPOAllocation` row with `from_po_line_ref = po_line.source_ref`,
`from_po_number = po.po_number`, `quantity_received` = the fixture's `qty_received` argument,
`line_status` / `receipt_status` derived from it. Existing tests in the four
`test_board_received_stock_s3_*.py` files keep their assertions; only the document name they
expect changes from the PO number to the SPO number where a test pins it.

New tests (one file, `test_board_received_stock_s3_spo_received.py`):

- **T1** PO line transferred (`qty_received = qty_ordered`), SPO row `quantity_received = 0`,
  on hand at own bin 1, Buy 7 posted -> Confirm succeeds, credit 0, no refusal (the SO399639
  shape).
- **T2** Same, SPO `quantity_received = 7`, on hand 7 -> refusal names the SPO number, credit 7.
- **T3** PO line with `qty_received = 7` and NO SPO row -> credit 0 (R1: PO received is never
  landed).
- **T4** Tier 2: a closed sibling's SPO row received 12 against ordered 10 -> spare 2 credited
  to the open line; the sibling's PO `qty_received` set to 99 does not change that.
- **T5** `_prefetch_own_arrival` and `_po_received_by_so_line_ref` return the same tuple for
  the same line (the batched and single reads agree).

## Open ruling (S3, reviewer 24 Sep)

Retired SPO rows (`retired_at` set, the old DocKey when AutoCount re-creates a shipping order)
keep their `quantity_received` and are counted by both R7 joins, the same way
`spo_supply.visible_line_clauses()` keeps them visible as real goods. On the 0921 copy 6
`from_po_line_ref` values carry both a retired and a live row with receipts, so those could
double-count. Built as A (count them, consistent with the board); owner may rule B (exclude
`retired_at IS NOT NULL` from R7 only).

## Out of scope

- The board proposing Buy for a late own-SPO (R2 keeps it).
- `spo_allocations.po_line_id` being NULL everywhere.
- The parent plan's Status line (still "in review" though #1092 merged) - archived separately.
