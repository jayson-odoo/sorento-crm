# PLAN: estimated delivery date stays in the CRM UI, never in MCP / turn API output

Status: merged (PR #800, 10 Sep 2026)
Domain: chatbot
Branch: fix/chatbot-eta-not-in-turn

## Problem

`orders.estimated_delivery_date` is not a real promise. The order import stamps it as
`order_date + 2 business days` (`order_service.py` ~2824) on every master row. The chatbot
turn engine then says it to the customer:

> Order PS202609-0213 (...) hasn't been delivered yet (estimated delivery 2026-09-14).

Owner ruling 10 Sep 2026: the date may show in the CRM UI. It must not be returned by MCP,
and must not reach the chatbot / turn API response.

## Where it leaks (measured)

| Path | State |
| --- | --- |
| `crm_order_management_orders_list` / `_get` (MCP) | already dropped, `_ORDERS_LIST_DROP_ROW_KEYS` (TCK-2026-000023) |
| `crm_order_management_orders_by_product_list` | `OrderSimpleRef` has no such field - clean |
| `entity_resolver.py` customer_order `display` (3 sites: ~1015, ~1883, ~3757) | LEAKS - reaches the turn engine in process (`services.resolve_entity`) and `GET/POST /system/references/resolve`. A fourth customer_order builder exists (trgm tier, ~3021) but its `display={}` never carried the field - nothing to drop there. |
| `answer.py` ~2859 `eta_text` in the delivered-status miss message | LEAKS - prints the resolver value |

## Change

1. `entity_resolver.py`: drop `estimated_delivery_date` from the three customer_order
   `display` dicts (and the column from their queries). `actual_delivery_date` stays.
2. `answer.py` `not_found_error_message`: remove `eta_text`. Message becomes
   `Order <code> (<customer>) hasn't been delivered yet - current status: <status>. Would you like me to escalate to <team> team?`
3. Tests: `TestStatusAwareMissMessageIncludesTheEtaDate` flips to assert the date is
   absent even when the display carries one; the `STATUS_MISS_MESSAGE_STATES_THE_ETA`
   divergence in `tests/chatbot/divergences.py` is rewritten to record the 10 Sep ruling;
   a resolver test asserts no customer_order display key `estimated_delivery_date`.
4. No MCP code change: the orders tools already drop it. No FE change: the order list /
   detail keep showing it.

UAC: `chatbot-eta-not-in-turn-acceptance-criteria.md`.
