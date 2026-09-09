# PLAN: "last in" answer carries the container number

Status: VERIFIED, PR pending (9 Sep 2026)
Branch: `feat/chatbot-last-in-container` (worktree `.claude/worktrees/chatbot-last-in-container`, base `origin/main` 181db68b6)
UAC: `chatbot-last-in-container-number-acceptance-criteria.md`
Parent: `PLAN-chatbot-warehouse-entity-and-last-in.md` (PR #757, merged 8 Sep 2026)

## Owner ruling (9 Sep 2026, verbatim)

> for our spo allocation MCP tool that answer this "Here is the last SPO line per product.
> SPO Number: SPO-2026/09-0034 / Product Code: CB6633-PP / SPO Quantity: 142 / SPO Date:
> 2026-08-20 / Warehouse: BRW", i think we need to answer the container number also which
> should appear in the container_number column in the SPO allocation, the container number
> can put below the SPO number in the answer

## What exists today (measured)

- `spo_allocations.container_number` VARCHAR(100) (D6, migration 477). Written by
  `shipping_order_ingest_service` on a shipping-order ingest, via
  `shipping_order_rules.extract_container_number`, and relinked by
  `procurement_service._relink_allocations_for_shipment` when an inbound shipment carrying
  the same container lands.
- On the 7 Sep prod copy (`sorento_ai_automation_0907`): 14 of 77,260 allocations carry a
  container number, all on `SPO-2026/09-0030` (CMAU7650091) and `SPO-2026/09-0031`
  (TCNU2593467), all created 7 Sep. Older lines have none, so the field is **"if any"**,
  exactly like `gr_quantity` / `gr_date`: absent, never rendered empty.
- `spo_last_receipt_service.last_receipt_rows` does not select the column. The presenter
  `_spo_last_receipt` (MCP) renders only what the row carries. The chatbot business lane
  and n8n print the envelope's `items[].fields[]` generically, so a new field needs no
  consumer change (grepped: no reader of this tool's row keys outside the presenter).

## Change (simplest thing)

1. `sorento_crm_backend/app/services/spo_last_receipt_service.py`: select
   `SPOAllocation.container_number` in BOTH branches (windowed per-product via the
   subquery, and unscoped), emit row key `container_number` (None when null). Docstring
   row-key list updated.
2. `sorento_crm_backend/app/api/v1/procurement/spo_allocations.py`: route docstring lists
   `container_number`.
3. `sorento_crm_mcp/sorento_crm_mcp/presenters.py` `_spo_last_receipt`: new pair
   `("container_number", "Container Number", r.get("container_number"))` inserted
   directly after `spo_number`, so the row reads:

       SPO Number, Container Number (if any), Product Code, SPO Quantity,
       GR Quantity (if any), SPO Date, GR Date (if any), Warehouse

   `b.item` drops a None value, which is what makes "if any" hold.
4. `sorento_crm_mcp/sorento_crm_mcp/catalog.py` tool description: "Each row reads in this
   order: spo_number; container_number (present ONLY when the line was ingested from a
   shipping order that named its container); product_code; ...".
5. Parent plan + UAC AC-9 amended to the new order (one sentence each, pointing here).

No migration, no frontend, no new endpoint, no n8n change.

## Tests (Phase 2, red first)

- `sorento_crm_backend/tests/test_spo_last_receipt.py`:
  - a line seeded with `container_number="CMAU7650091"` answers `container_number` on
    the per-product branch AND on the unscoped branch;
  - a line with no container answers `container_number is None`;
  - the route (`GET .../last-receipt`) carries `data[0].container_number`.
- `sorento_crm_mcp/tests/test_presenters.py`:
  - exact-order test becomes the 8-label list above (with a container);
  - a row without `container_number` renders the previous 7-label list unchanged (and the
    open-line 5-label test stays as is, proving absence);
  - `Container Number` sits at index 1, directly under `SPO Number`.

## Verification

- pytest: `tests/test_spo_last_receipt.py` (backend venv, blank-schema fixture) and
  `tests/test_presenters.py` (run with `PYTHONPATH=<worktree>/sorento_crm_mcp`, see
  memory `project_lane_backend_imports_primary_mcp_catalog`).
- Live: boot the lane backend + MCP on :8080/:8765 with that PYTHONPATH, call the MCP
  tool for a product on `SPO-2026/09-0030`, and read `Container Number: CMAU7650091` on the
  line under `SPO Number`.

## Verification record (9 Sep 2026)

- Red first: 4 backend + 1 presenter test failed before the code change; green after.
  Backend `test_spo_last_receipt.py` 22 passed; MCP suite 414 passed.
- Live (AC-8): lane backend :8082 + MCP :8766 (PYTHONPATH on the worktree's mcp package),
  0907 copy. `view=render` for CB6633 rendered `SPO Number: SPO-2026/09-0033` then
  `Container Number: TCNU2951576`, then Product Code / SPO Quantity / SPO Date (recorded) /
  Warehouse. CB6633-PP (last line SPO-2026/08-0002, no container) rendered the seven-field
  row with no Container Number line. Raw (no `view`) payload carries
  `container_number` as a key on both, null on the second.

## Review rounds

- Round 1: reviewer (Opus) on the uncommitted diff - see PR body.
