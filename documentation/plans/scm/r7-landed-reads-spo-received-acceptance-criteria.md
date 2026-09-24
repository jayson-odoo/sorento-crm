# UAC: R7 own-arrival credit reads SPO received

Plan: `PLAN-r7-landed-reads-spo-received.md`. All verified by pytest on Postgres (`tests/scm/`).

- **AC-1** A sales-order line whose purchase-order line is fully transferred to an SPO
  (`purchase_order_lines.qty_received = qty_ordered`) with `spo_allocations.quantity_received = 0`
  has an own-arrival credit of 0. Confirming a Buy for the line's whole open quantity succeeds.
- **AC-2** When that SPO row's `quantity_received` is N > 0, the credit is min(N, open qty, on
  hand at the line's own bin), and a Buy left uncovered by a Reserve at that bin is refused with
  a message naming the SPO number, never the PO number.
- **AC-3** A purchase-order line with `qty_received > 0` and no SPO row carrying its `source_ref`
  as `from_po_line_ref` contributes 0 to the credit.
- **AC-4** Tier 2 sibling spare is computed off the sibling's SPO received, not its PO received.
- **AC-5** The batched prefetch (`_prefetch_own_arrival`) and the single read
  (`_po_received_by_so_line_ref`) return the same (qty, document) for the same line.
- **AC-6** Product and company filters hold on the SPO join exactly as on the PO read: an SPO
  row for another product or another company is never counted.
- **AC-7** Every existing test in `tests/scm/test_board_received_stock_s3_*.py` is green after the
  fixture change, with only document-name expectations updated.
- **AC-8** `planning_change_service._refuse_buy_over_own_arrival`'s message names the same
  document the confirm path names.
