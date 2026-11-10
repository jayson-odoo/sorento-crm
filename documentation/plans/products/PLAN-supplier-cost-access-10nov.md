# PLAN: Supplier tab and cost data restricted to purchasing and management

Status: Plan (behaviour card pending owner answers). Track: full (RBAC change + data migration).

Lane: SUPPLIER-COST-ACCESS. Source: owner + management meeting 9 Nov 2026, relayed 10 Nov.

## Decisions (owner relayed)

1. The product Supplier tab (suppliers, unit costs, last purchase / PO costs) is visible only to
   purchasing and management roles. Marketing and sales roles do not see it. Dealers never see cost.
2. History still shows THAT a cost / supplier change happened (who, when, which field), but the
   values are masked for users without the cost permission. Raw JSON stays admin-only.

Surface inventory, permission design and tests follow below once the behaviour card is posted.
