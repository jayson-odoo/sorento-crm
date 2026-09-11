# PLAN: PO placed fields and cross-domain rung wording

Status: implemented (PR pending)
Branch: `fix/po-placed-fields-and-rung-wording` (worktree `.claude/worktrees/po-placed-fields`)
UAC: `po-placed-fields-and-rung-wording-acceptance-criteria.md`

## Owner ruling (11 Sep 2026, from a live turn on SRTWC191-G3)

1. `crm_procurement_po_placed_list` renders per row, in order: Company (when present), PO
   Number, Product Code, Ordered Qty, Outstanding Qty, PO Date, Location, Supplier
   (restricted `purchase_orders.supplier`, unchanged). Source (`kind`) and Expected Date
   are dropped from the rendered fields. `kind`, when the row has one, moves to the ITEM's
   own top level (sibling of `title`/`fields`/`flags`) so the chatbot rung can still tell a
   PO row from an SPO row with no rendered Source field.
2. The cross-domain PO rung answers as one field per line per row - `Product Code:`,
   `Ordered:`, `Outstanding:`, `PO date:`, `Location:` - rows separated by ONE blank line.
   A null or empty `ordered_qty`, `po_date` or `location` omits that line entirely (never a
   placeholder); `Product Code:` and `Outstanding:` always print. This retires the old
   `Qty N placed on DATE` shape.
3. `purchase_orders_placed_rows` (backend) adds `ordered_qty` and `location` to every row:
   PO side from the line's own `qty_ordered` and its warehouse code (via a new outerjoin,
   None when the line has no warehouse or the warehouse falls outside the caller's company
   scope); SPO side from the allocation's `allocated_quantity` and its warehouse code, else
   the book's raw `location_code`, else None.

## Files touched

- `sorento_crm_backend/app/services/purchase_order_service.py` - `ordered_qty` + `location`
  on both the PO and SPO row-building loops, plus a `Warehouse` outerjoin on both queries.
- `sorento_crm_mcp/sorento_crm_mcp/presenters.py` - `_purchase_orders_placed` field order,
  drops Source/Expected Date, stamps `kind` on the item's top level.
- `sorento_crm_mcp/sorento_crm_mcp/catalog.py` - `crm_procurement_po_placed_list`
  description's field list and date-window note.
- `sorento_crm_backend/app/services/chatbot/lanes/business/answer.py` -
  `_crossdomain_rung_row` reads `kind` from the item's top level only (no fallback);
  `_crossdomain_rung_text` renders the structured per-row block.
- Tests: `sorento_crm_mcp/tests/test_presenters.py`,
  `sorento_crm_backend/tests/test_purchase_orders_placed.py`,
  `sorento_crm_backend/tests/chatbot/test_crossdomain_ladder.py`,
  `sorento_crm_backend/tests/chatbot/test_foundre_rung_end_to_end.py`,
  `sorento_crm_backend/tests/chatbot/console_cases/2026-09-07-growth-r1.yaml` (expectations
  only, not pytest-collected).

## Not observed live

The multi-row, blank-line-separated block is unit-tested only. Every candidate product in
the lane DB (`sorento_ai_automation_popf`) that carries several open PO lines - e.g.
SRTWCY7405-PJ, named in the review brief - also holds real physical stock at several
locations, so the chatbot answers on the stock rung and the PO rung never fires for it; see
`documentation/plans/chatbot/evidence/po-placed-fields-11sep/console-check.md` section C.
The underlying multi-row data and the single-row live turn (SRTWC191-G3, section B of that
file) both confirm the shape; the multi-block chat rendering itself was confirmed at the
unit-test level (`TestOwner11SepTheRungRendersStructuredFieldsPerRow`), not against a live
turn.
