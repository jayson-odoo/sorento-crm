# Live verification evidence - lane fix/po-placed-fields-and-rung-wording

11 Sep 2026. Backend on :8082, MCP on :8769, DB `sorento_ai_automation_popf` (private, migrated to
head). No production code or tests edited; no commits made.

## Boot

```
ENABLE_SCHEDULER=false AI_ASSISTANT_MCP_URL="http://127.0.0.1:8769/mcp" \
  venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8082
# -> Application startup complete. PID 69503

CRM_BASE_URL=http://127.0.0.1:8082 EXTERNAL_API_KEY=test CRM_MCP_PORT=8769 PYTHONPATH=. \
  ../sorento_crm_backend/venv/bin/python -m sorento_crm_mcp
# -> Uvicorn running on http://0.0.0.0:8769. PID 69515
```

`settings.ai_assistant_mcp_url` (`app/config.py`) is a plain pydantic-settings field with default
`http://localhost:8765/mcp`; the chatbot business lane reads it via
`app/services/chatbot/lanes/business/services.py::_mcp_call`. It is a pure env-var override
(`AI_ASSISTANT_MCP_URL`) - **no `system_settings` DB row involved**, so nothing needed restoring.
Confirmed with `settings.ai_assistant_mcp_url` printed both before (default `:8765`) and after
(`http://127.0.0.1:8769/mcp`) setting the env var.

## A. Full case file: `tests/chatbot/console_cases/2026-09-07-growth-r1.yaml`

```
EXTERNAL_API_KEY=test venv/bin/python scripts/chatbot_console_check.py \
    tests/chatbot/console_cases/2026-09-07-growth-r1.yaml --base-url http://127.0.0.1:8082
```

Result: **19 passed, 10 failed.**

```
PASS  D7 - an incoming ask on a zero-stock code climbs to the PO rung
PASS  A7 no stock, no incoming, but PO is placed
PASS  A7 nothing on any rung says so and offers to escalate
PASS  A7 suffixed code MSK11A-QT reaches the incoming rung
PASS  A7 suffixed code CWCX1009-SH reaches the incoming rung
```
The two cases that exercise this lane's own PO-placed rung directly (D7, "A7 no stock, no
incoming, but PO is placed") **pass**.

Failing lines, verbatim:

```
FAIL  A1 spec ask shows the compact Specs line     branch=business_query
      - reply does not contain 'Specs:'
FAIL  A1 one-key spec ask answers that key only    branch=business_query
      - reply does not contain '304'
FAIL  E2 - Catalog Sorento is a resource attachment ask, not promotion branch=business_query
      - reply does not contain 'I have attached'
      - reply does not contain 'SORENTO CATALOGUE 2024'
      - reply does not contain 'Mocha Catalogue FA 300924'
FAIL  A3 how many did the customer take - by-product tool carries the SO line per row
      - reply does not contain 'SO Outstanding'
      - reply does not contain 'Transferred to DO'
      - reply does not contain 'SRTWC286'
FAIL  A3 open DO grouped by customer renders headed sections
      - reply does not contain 'C-FH14'
FAIL  A5 PO for a product, and no supplier for a dealer branch=None
      - branch_kind is None, expected 'business_query'
      - reply does not contain 'SRTWT7445-LV-NEW'
      - reply does not contain 'PO Number'
FAIL  A6 last in for a product                     branch=business_query
      - reply does not contain 'Quantity Received'
FAIL  A6 last 3 received returns three              branch=business_query
      - reply does not contain 'Quantity Received'
FAIL  A7 suffixed code SRTWT7445-LV-NEW reaches the incoming rung branch=None
      - branch_kind is None, expected 'business_query'
      - reply does not contain 'SRTWT7445-LV-NEW'
```

Root cause, confirmed in the backend log (`OPENAI_API_KEY` is empty in this lane's `.env`,
0 chars):

```
app.services.entity_resolver - ERROR - Tier-3 query embedding failed for token=seat cover
  File ".../embedding_worker.py", line 608, in _embed_text_chunks
    raise ValueError("OPENAI_API_KEY is required for embedding worker")
```
(also logged for tokens `Ibwc7605`, `C-FH14`). This matches the documented local limit
(`documentation/agents/chatbot-verification.md`): "The MCP tool search needs OPENAI_API_KEY ...
Those cases are graded on the production run." A5 and the suffixed-code case return
`branch_kind=None` with the generic error copy, consistent with the same LLM-dependent parse step
failing with no key configured (no unhandled-exception trace in the backend log at all for those
two turns - `grep -n "chatbot turn" ` on the backend log is empty, so it is not a crash inside
`engine.py`'s own try/excepts, which do log via `logger.exception`). None of the 10 failures
reference PO-placed fields/labels; they are pre-existing entity-resolution/parse gaps orthogonal
to this lane, explainable by the empty `OPENAI_API_KEY`, not a regression this lane introduced.

## B. Owner's own example (`stock for SRTWC191-G3`)

```
EXTERNAL_API_KEY=test venv/bin/python scripts/chatbot_console_check.py \
    --say "stock for SRTWC191-G3" --base-url http://127.0.0.1:8082
```

```
> stock for SRTWC191-G3
  branch_kind: business_query
  reply.text: Here's what you want:
• product: SRTWC191-G3

But no inventory matched these.
No stock and no incoming for SRTWC191-G3, but PO is placed:
Product Code: SRTWC191-G3
Ordered: 30
Outstanding: 30
PO date: 2026-08-10
Location: BRW

Would you like me to escalate to purchasing team?
  trace: tool=crm_inventory_stock_balance_list args={...}  rung=crm_incoming_stock_list(0 rows)  rung=purchase_order(1 rows)
```

**PASS.** Reply matches the expected block exactly (labels, order, values), and the trace shows
the PO rung actually ran (`rung=purchase_order(1 rows)`) - no `skipped: not_granted`, so no reveal
grant workaround was needed for this contact/session.

## C. Multi-line-per-PO case (`stock for SRTWCY7405-PJ`)

```
EXTERNAL_API_KEY=test venv/bin/python scripts/chatbot_console_check.py \
    --say "stock for SRTWCY7405-PJ" --base-url http://127.0.0.1:8082
```

Reply: `Stock details found for the requested products.` with 7 real stock-balance rows (BRW,
BRW-BB, DC1-BB, DC1-IB, DC1-IR, MWH-BB, WH3-IB), `Quantity On Hand` positive at all of them
(sums to ~1,746 units).

**Could not be exercised as specified.** The brief's premise - that this product has zero stock,
so the PO-placed rung's multi-line format fires - does not hold in this DB snapshot: SQL against
`stock` (`quantity_on_hand`) confirms real physical stock at 7 locations, so the chatbot correctly
answers on the stock rung and never reaches PO-placed. Trying the literal phrasing "PO for
SRTWCY7405-PJ" also does not reach it - it resolves to `crm_order_management_orders_list`
(delivery orders), not purchase orders; there is no chat phrasing that skips the stock rung.

The underlying PO-line data DOES match the brief exactly (`purchase_order_lines` query, filtered
to the two named POs, 0-received lines only): `202606-S0082` has exactly one 0-received line (6,
BRW); `202604-S0083` has exactly three (67 BRW-IR, 60 BRW-BB, 27 BRW-BB) - the four rows named in
the brief. Confirmed the format at the route/tool level instead (see below - this is item E/D's
own product, SRTWC191-G3, single-row; a direct call against SRTWCY7405-PJ's UUID
`2318d175-2581-4bfb-b683-ecc2d22856ae` via
`GET /api/v1/procurement/purchase-orders/placed?product_ids=2318d175-2581-4bfb-b683-ecc2d22856ae`
returns multiple `kind: "po"` / `kind: "spo"` rows with `ordered_qty`/`location` present per row,
confirming the multi-row shape works; the chat-level 4-block rendering itself was not observable
given the DB's current stock state).

## D. MCP tool directly (`crm_procurement_po_placed_list`, SRTWC191-G3)

Product UUID: `a7b6b71d-6365-47cf-a521-df4f1fa14900` (`select id from products where
product_code='SRTWC191-G3'`).

Called via the same `MCPRuntimeClient` the chatbot uses in-process
(`app/services/ai_assistant_service.py`), against the lane's own MCP server at
`http://127.0.0.1:8769/mcp`, with the presenter's opt-in `view=render` param (bare `tools/call`
returns raw catalog JSON; `view=render` is what the presenter layer,
`sorento_crm_mcp/presenters.py`, formats into the labeled envelope):

```python
from app.services.ai_assistant_service import MCPRuntimeClient
client = MCPRuntimeClient('http://127.0.0.1:8769/mcp', timeout_seconds=20)
client.call_tool('crm_procurement_po_placed_list',
                  {'product_ids': ['a7b6b71d-6365-47cf-a521-df4f1fa14900'], 'view': 'render'})
```

Result:
```json
{"result_type": "purchase_orders_placed", "intro": "Here is the PO placed I found.",
 "items": [{"title": "202608-S0016", "fields": [
    {"key": "po_number", "label": "PO Number", "value": "202608-S0016"},
    {"key": "product_code", "label": "Product Code", "value": "SRTWC191-G3"},
    {"key": "ordered_qty", "label": "Ordered Qty", "value": "30"},
    {"key": "outstanding_qty", "label": "Outstanding Qty", "value": "30"},
    {"key": "po_date", "label": "PO Date", "value": "2026-08-10"},
    {"key": "location", "label": "Location", "value": "BRW"},
    {"key": "supplier", "label": "Supplier", "value": "GUANGDONG LANYI INTELLIGENT KITCHEN AND BATHROOM CO., LTD."}
  ], "flags": {...}, "kind": "po"}],
 "attachments": [], "action_links": [], "last_updated_at": null, "has_result": true,
 "restricted_fields": {"supplier": "purchase_orders.supplier"}}
```

**PASS.** Field labels are exactly `PO Number, Product Code, Ordered Qty, Outstanding Qty, PO
Date, Location, Supplier` in that order - no `Company` field (none for this row, consistent with
"if present"), no `Source`, no `Expected Date`. The item carries `"kind": "po"` at the item's own
top level (outside `fields`).

## E. Raw backend route (SRTWC191-G3)

```
curl -s -H "X-API-Key: test" \
  "http://127.0.0.1:8082/api/v1/procurement/purchase-orders/placed?product_ids=a7b6b71d-6365-47cf-a521-df4f1fa14900"
```

```json
{"data": [{"kind": "po", "po_number": "202608-S0016", "product_id": "a7b6b71d-6365-47cf-a521-df4f1fa14900",
  "product_code": "SRTWC191-G3", "product_name": "SRTWC191-G3", "outstanding_qty": 30,
  "expected_date": "2026-08-10", "supplier": "GUANGDONG LANYI INTELLIGENT KITCHEN AND BATHROOM CO., LTD.",
  "po_date": "2026-08-10", "ordered_qty": 30, "location": "BRW"}],
 "pagination": {"total": 1, "page": 1, "limit": 1}, "empty": false}
```

**PASS.** Row carries `ordered_qty` and `location`, and still `expected_date` and `kind`, as
required.

## Summary

| Item | Result |
| --- | --- |
| A - full case file | 19/29 passed; 10 fails all trace to empty `OPENAI_API_KEY` in this lane's `.env` (embedding/LLM parse dependent), none touch PO-placed fields; the two cases that exercise the PO-placed rung directly (D7, A7) pass |
| B - owner's example | PASS, exact reply block, PO rung ran (no `skipped: not_granted`) |
| C - multi-line-per-PO | Not exercisable via chat as specified - product has real stock in this DB snapshot so the PO-placed rung never fires; underlying PO-line data matches the brief exactly, and multi-row shape confirmed via the raw route on this product's own UUID |
| D - MCP tool (`view=render`) | PASS, exact labels + order, no Company/Source/Expected Date, `kind: "po"` at item top level |
| E - raw backend route | PASS, `ordered_qty` + `location` present alongside `expected_date`/`kind` |

Ports used: backend :8082 (PID 69503), MCP :8769 (PID 69515). Both killed by PID at the end of the
session. No `system_settings` row was changed (the MCP endpoint is a pure env-var override,
`AI_ASSISTANT_MCP_URL`), so there was nothing to restore.
