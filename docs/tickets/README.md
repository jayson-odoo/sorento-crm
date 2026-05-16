# Ticket specs

Per-ticket solution markdowns. Each is self-contained so an independent Claude Code agent can pick it up with no extra context.

Source ticket bodies live in the in-CRM ticketing system at `/ticket-management/tickets` (table `tickets`). Specs reference them by `ticket_number`.

| Ticket | Title | Priority | Status | Spec |
|--------|-------|----------|--------|------|
| TCK-2026-000015 | MCP attachment / catalogue chunking | medium | draft | [TCK-2026-000015.md](./TCK-2026-000015.md) |
| TCK-2026-000016 | Promotion MCP: drop discount fields + dynamic `access_levels` | high | draft | [TCK-2026-000016.md](./TCK-2026-000016.md) |
| TCK-2026-000017 | `crm_incoming_stock_by_product`: embedding pre-resolve + ilike | medium | draft | [TCK-2026-000017.md](./TCK-2026-000017.md) |
| TCK-2026-000018 | n8n SLA routing: technical drawing → marketing_product | low | draft | [TCK-2026-000018.md](./TCK-2026-000018.md) |
| TCK-2026-000019 | Packing list + promotion email: warn on unknown products | high | draft | [TCK-2026-000019.md](./TCK-2026-000019.md) |
| TCK-2026-000020 | Attachments: dup-name + uniform replace-with-webhook-retrigger | high | draft | [TCK-2026-000020.md](./TCK-2026-000020.md) |
| TCK-2026-000021 | (DROPPED — bidirectional SPO↔packing-list matching) | — | deleted | — |
| TCK-2026-000022 | `.xlsm` intake: strip macros, save cleaned `.xlsx` | medium | draft | [TCK-2026-000022.md](./TCK-2026-000022.md) |
| TCK-2026-000023 | Orders: `delivery_time` → `pickup_time` rename + MCP trim | high | draft | [TCK-2026-000023.md](./TCK-2026-000023.md) |
| TCK-2026-000024 | Orders MCP: customer + product wildcard via embedding | medium | draft | [TCK-2026-000024.md](./TCK-2026-000024.md) |
| TCK-2026-000025 | GRN MCP: limit default, ilike product, rename + trim (MCP-only) | high | draft | [TCK-2026-000025.md](./TCK-2026-000025.md) |
| TCK-2026-000026 | Embedding: customer + transporter coverage | high | draft | [TCK-2026-000026.md](./TCK-2026-000026.md) |
| TCK-2026-000027 | Orders MCP: search by `actual_delivery_date`, not `order_date` | medium | draft | [TCK-2026-000027.md](./TCK-2026-000027.md) |

## Dependency map

```
26 (customer + transporter embedding)
  ├── 17 (incoming stock fuzzy product search — product already embedded, can ship without 26)
  └── 24 (orders fuzzy customer/product/transporter — needs 26 for transporter)

20 standalone (attachments + uniform replace-with-webhook-retrigger)
21 DROPPED
22 standalone (.xlsm intake)
23 standalone but DB-migration-heavy (delivery_time → pickup_time)
25 standalone MCP-only (GRN rename + ilike)
27 standalone (date-filter description tightening)
```

## Parallel execution

Each spec is hand-off ready: open `TCK-2026-000XXX.md` and the agent has goal, files, step-by-step, acceptance, and verification. Spin up an agent per ticket and they should not collide on shared files except where listed:

- 17 + 24 + 25 share a fuzzy-resolver helper (factor in `app/services/fuzzy_resolver.py`); whichever ticket lands first owns the helper, others import.
- 15 + 16 + 23 + 25 + 27 all touch `sorento_crm_mcp/sorento_crm_mcp/server.py` and `catalog.py` — straightforward merges; coordinate on the shared `_sanitize_tool_response()` dispatch table.
