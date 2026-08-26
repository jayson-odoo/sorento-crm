# PLAN - S12: what the salesperson gets back on WhatsApp now that PO, SPO and PI are in the system

Status: DRAFT 2026-08-26, for the captain's glance before build. Builds after the scm-uat stack is rebased onto main (needs #298, stock visibility policy, merged 25 Aug 12:22 UTC after the lane branched).
Lane: `.claude/worktrees/scm-uat` (FE :3080, BE :8080, MCP :8765 from the same venv).
UAC: `scm-whatsapp-stock-answers-acceptance-criteria.md` (alongside). Friday station 12 in `PLAN-scm-friday-uat-journey.md`.

## 0. What the captain asked (26 Aug)

1. When a salesperson checks stock and there is no stock and no incoming, say whether there is a PO, now that the PO book is in the system.
2. Show the outstanding SO quantity beside the quantity on hand on a stock check.
3. Answer "last incoming cost" from the proforma invoice, now that PIs are in the system.

## 1. What exists (verified 26 Aug)

| Fact | Where |
| --- | --- |
| The bot's stock answer is `crm_inventory_stock_balance_list` (MCP) over `GET /api/v1/inventory/stock-balance`; rows carry the AutoCount quantities per warehouse (on hand, and the SO / SPO columns the board popover already prints as `so_qty` / `spo_qty` / `available_qty`). | `sorento_crm_mcp/catalog.py`, `app/api/v1/inventory/stock.py`, `project_fulfilment_board_service._location` |
| The stock visibility policy (#298) runs a sanitizer BEFORE the presenter and decides per contact / per access type which quantities a contact may see (it deletes `available` for some modes). | `sorento_crm_mcp/server.py:_sanitize_tool_response`, backend `contact_access_type_service` |
| Incoming supply is `scm.on_order_v` over `spo_allocations` (SPO documents live there since migration 420; an overdue promise still counts, and reads "overdue N days"). The bot already has `crm_incoming_stock_by_product`. | `spo_supply.py`, `presenters._incoming_by_product` |
| Open PO balance per product and warehouse, net of order-inquiry links, is computed for the board popover (`po_open_qty`: active / partial POs, open lines, drafts excluded). | `project_fulfilment_board_service._open_po_balance` |
| Proforma invoice lines carry `unit_price`, `qty`, `po_ref`, `product_id`; the header carries `supplier_id`, `pi_number`, `invoice_date`, `currency`, `block_index` (a multi-block file is several headers). `summary_order_service._last_incoming_cost` reads the newest INBOUND SHIPMENT line cost per supplier, not the PI. | `app/models/scm.py:1336-1456`, `summary_order_service.py:1286` |
| The bot has no cost tool and no PO tool for a salesperson. | `catalog.py` |

## 2. Design (simplest thing)

### S12a. One stock answer, five numbers
`GET /inventory/stock-balance` rows gain, per warehouse: `outstanding_so_qty` (AutoCount SO column), `incoming_qty` (open SPO allocations at that warehouse, `on_order_v`), `incoming_next` (the earliest SPO number + expected date, overdue days when past), `po_open_qty` and `po_next` (earliest active PO line's number + expected date, net of links). One read each, reusing `_open_po_balance` and `spo_supply.open_incoming_clauses`; both readers moved to a small `app/services/inventory/supply_signals.py` so the board and the bot cannot disagree. Declared on the response schema.

The presenter prints, per warehouse: `On hand 12 · Outstanding SO 30 · Available -18 · Incoming 100 (SPO-2026/08-0061, 1 Aug, overdue 25 days)`; when incoming is 0 and on hand is 0: `On PO: 202608-S0015, 500 expected 4 Sep`; when neither: `Nothing on order`. No sentence explaining the columns.

The sanitizer (#298) keeps its authority: a contact who may not see `available` also does not see `outstanding_so_qty`; PO and SPO lines are shown only to modes that may see incoming (add the two keys to the policy's field map, default hidden for dealer contacts, shown for staff).

### S12b. Last incoming cost
New MCP tool `crm_scm_last_incoming_cost` over `GET /api/v1/scm/products/{product}/last-incoming-cost`: newest proforma invoice line for the product (by `invoice_date`, then `pi_number`), returning supplier, PI number, date, unit price, currency, qty, cited PO; plus the previous one for the same supplier when it exists (so the answer reads "RMB 65.50 on KL20260717 (17 Jul), was RMB 63.00 on KL20260402"). Falls back to the inbound shipment cost (`_last_incoming_cost`) with `source: shipment` when no PI names the product. Staff-only: the tool is gated by access type (the same policy table), never offered to a dealer contact.

### S12c. n8n
The system prompt for the sales bot names the two behaviours in one line each: stock questions call the stock tool and read the five numbers as they come; cost questions call the cost tool; nothing is computed in the prompt. Test via the n8n test workflow with pinned data before promotion (captain promotes).

## 3. Workstreams
- **S12a** BE fields + `supply_signals.py` + presenter + policy field map (BE + MCP, one day).
- **S12b** cost endpoint + MCP tool + seeding of the tool row (BE + MCP, half a day).
- **S12c** prompt + n8n test run (half a day, needs the captain for promotion).

## 4. Tests
- pytest: stock-balance rows carry the five numbers, declared on the schema; PO next excludes drafts and SPO documents; incoming reads overdue rows; cost endpoint newest-first with previous-for-supplier and the shipment fallback; access-type gating (dealer contact 403 on cost, sanitized stock).
- MCP tests: presenter wording for the three states (incoming, PO only, nothing); tool catalog entry; sanitizer keeps hiding `available` and the new keys per mode.
- n8n: one test execution per question type on the three Friday items (SRTWCY7405-PJ incoming, SRTWT7443 cost from KL20260717, one item on PO only).

## 5. Questions (captain)
- **QS1** Cost visible to which contacts: staff only (default), or also dealers? Default staff only.
- **QS2** Currency: show the PI currency as keyed (RMB) or convert to MYR with the book rate? Default as keyed.
- **QS3** When both a PO and an SPO exist, show both lines or the nearest only? Default both, nearest first.
