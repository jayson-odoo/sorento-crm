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
| TCK-2026-000021 | (DROPPED - bidirectional SPO↔packing-list matching) | - | deleted | - |
| TCK-2026-000022 | `.xlsm` intake: strip macros, save cleaned `.xlsx` | medium | draft | [TCK-2026-000022.md](./TCK-2026-000022.md) |
| TCK-2026-000023 | Orders: `delivery_time` → `pickup_time` rename + MCP trim | high | draft | [TCK-2026-000023.md](./TCK-2026-000023.md) |
| TCK-2026-000024 | Orders MCP: customer + product wildcard via embedding | medium | draft | [TCK-2026-000024.md](./TCK-2026-000024.md) |
| TCK-2026-000025 | GRN MCP: limit default, ilike product, rename + trim (MCP-only) | high | draft | [TCK-2026-000025.md](./TCK-2026-000025.md) |
| TCK-2026-000026 | Embedding: customer + transporter coverage | high | draft | [TCK-2026-000026.md](./TCK-2026-000026.md) |
| TCK-2026-000027 | Orders MCP: search by `actual_delivery_date`, not `order_date` | medium | draft | [TCK-2026-000027.md](./TCK-2026-000027.md) |
| TCK-2026-000028 | Form SLA: fix auto-scan tier progression + manual escalate | high | draft | [TCK-2026-000028.md](./TCK-2026-000028.md) |
| TCK-2026-000029 | SLA notifications via WhatsApp (escalation + assignment) | high | draft | [TCK-2026-000029.md](./TCK-2026-000029.md) |
| TCK-2026-000030 | Conversation SLA daily summary via WhatsApp (bounded template) | high | draft | [TCK-2026-000030.md](./TCK-2026-000030.md) |
| TCK-2026-000031 | User ↔ RespondContact link + admin phone + per-channel prefs | high | draft | [TCK-2026-000031.md](./TCK-2026-000031.md) |
| TCK-2026-000032 | Management KPI dashboard (SLA metrics from event logs) | high | draft | [TCK-2026-000032.md](./TCK-2026-000032.md) |
| TCK-2026-000033 | PWA enablement + web-push notifications | high | draft | [TCK-2026-000033.md](./TCK-2026-000033.md) |
| TCK-2026-000034 | Deferred director directives (backlog) | backlog | parked | [TCK-2026-000034.md](./TCK-2026-000034.md) |

## Acceptance criteria (loop-validated)

Testable UAC for TCK-28..33 live in [`UAC/`](./UAC/README.md) - functional / business / data / RBAC / UX / scalability criteria, each with a `Validate:` step (pytest / curl / Playwright MCP / psql). The `/loop` executing these plans must validate development against them: a criterion is `[x]` only when its validation passes; ticket Done = all criteria green + three-phase tests committed.

## SLA / notifications epic (directors' session 2026-06-17)

```
31 (user↔respond_contact link + phone + per-channel prefs)  ← land FIRST, foundation
  ├── 29 (WhatsApp on escalation + assignment)   needs 31 for recipient phones; OK is WhatsApp-side only (no CRM ack)
  └── 30 (conversation SLA summary via WhatsApp)  needs 31 for notify_whatsapp_summary toggle; bounded template + deep link

28 (form SLA manual escalate)   standalone; 29 wires WhatsApp onto its escalation event
32 (management KPI dashboard)   standalone (reads existing event logs); richer breakdowns use 31
33 (PWA + web push)             standalone; lights up the existing unused web_push delivery channel
34 (backlog)                    parked: feature voting, KPI-driven tasks, on-field Meta onboarding, HR module
```

Recommended order: **31 → (28, 32, 33 in parallel) → 29 → 30**.

## Dependency map

```
26 (customer + transporter embedding)
  ├── 17 (incoming stock fuzzy product search - product already embedded, can ship without 26)
  └── 24 (orders fuzzy customer/product/transporter - needs 26 for transporter)

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
- 15 + 16 + 23 + 25 + 27 all touch `sorento_crm_mcp/sorento_crm_mcp/server.py` and `catalog.py` - straightforward merges; coordinate on the shared `_sanitize_tool_response()` dispatch table.
