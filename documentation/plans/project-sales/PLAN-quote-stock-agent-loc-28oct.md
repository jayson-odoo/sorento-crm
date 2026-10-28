# PLAN: quotation line stock limited to the user's allowed locations (QUOTE-STOCK-AGENT-LOC)

Status: Plan. Behaviour card filed to the owner, waiting on the open questions. Track: M rule change,
but a new permission needs a seed migration, so the L steps apply (migration checked on a dev copy,
security-reviewer).

## Owner rulings

- 28 Oct ~19:00: "i want to comment on quotation, i think to check stock right, should base on the
  location group of the sales agent of the user, simple as that, cannot simply let them check other
  locations"
- 28 Oct ~19:10: "if a user with no linked agent then cannot see stock, if got several agent then can
  see combination of different groups, certain permission can see the stocks, actually should depend
  on the location allowed for this contact la, that's the source of truth"

## What exists today (origin/main 9e41d84fc2)

- Selector: `sorento_crm_frontend/app/(protected)/project-sales/[projectId]/components/QuotationStockChip.tsx:48`
  (`useQuotationStockGroup`, remembered per browser in localStorage) and `:63` (`StockAtSelect`, option
  label `<group> group + site pools`). Drawn in the Lines toolbar, `QuotationLinesGrid.tsx:991`.
- Group list: `_shared/hooks/useFulfilmentPlanning.ts:451` (`useStockGroups`): the suffix of every
  active fulfilment-planning warehouse. Any group, any user.
- Line figure: `QuotationStockChip.tsx:142` reads `useStockDetail(product, null, null, group)`, i.e.
  `GET /api/v1/project-sales/fulfilment-planning/stock-detail?group=<G>`
  (`sorento_crm_backend/app/api/v1/projects/fulfilment_planning.py:952`), gated only by
  `projects.projects.view` (`:87`). The same endpoint feeds the fulfilment board's stock drill.
- Popover: adds the site pools (`QuotationStockChip.tsx:224`, `group=pools`) and AutoCount's figures
  (`useStockStatus`, `GET /api/v1/inventory/stock-status`), and `withAutoCount`
  (`_shared/lib/autoCountStock.ts:33`) appends EVERY other AutoCount location as an "Other group" row.
- User -> agent: `users.respond_contact_id` -> `sales_agents.contact_id`
  (`app/models/sales_agent.py:99`; resolvers `app/services/sales/portal_agent.py:24`
  `agents_for_contact` (all active agents) and `:65` `agent_for_user` (first one only)).
- Agent location group: `sales_agents.location_group` (`app/models/sales_agent.py:92`), the warehouse
  suffix (`AM` = BRW-AM, DC1-AM, MWH-AM, WH3-AM).
- Contact allowed locations: the Stock visibility policy, `stock_visibility_policies`
  (`app/models/access.py:866`), resolved by `app/services/stock_visibility.py:229` `resolve_policy`:
  contact override > merged access types (most restrictive) > global default. `warehouse_ids` NULL =
  all, `excluded_warehouse_ids` = all except. Edited on the contact page (Stock visibility section,
  `components/stock-visibility/StockVisibilitySection.tsx`) and per access type. Today it drives the
  chatbot's stock answers.
- No "see all stock" permission exists. Admin/superadmin pass every `require_permission`
  (`app/dependencies.py:414`). Permissions are registered in `app/rbac/permission_registry.py` and
  seeded to roles by a migration (pattern: `alembic/versions/sat_0001_stock_ask_done.py`).

## Proposed rule (pending the card answers)

For a user without the new permission (and not admin/superadmin):
1. No linked active agent -> no stock on any quotation line, and no selector.
2. Linked agent(s) -> the locations allowed for the user's contact (`resolve_policy`), only the
   warehouse set; the chatbot's mode and hide-zero settings do not apply here.
3. Line figure = Available summed over those locations; the popover lists only those locations
   (no "Other group" rows outside the set). No selector.
4. Enforced on the server: the quotation's stock read computes the set itself; the browser never
   names the locations.

With the permission (or admin/superadmin): today's selector and figures, unchanged.

## Open questions

See the behaviour card (crew ask, 28 Oct). Answers recorded here once relayed.

## Next

UAC file alongside, tickets, red tests (tester), coder, kill test, reviewer + security-reviewer,
agent-browser 1280/375 on the crew copy, hand-test script.
