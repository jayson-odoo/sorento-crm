# PLAN: quotation line stock limited to the user's allowed locations (QUOTE-STOCK-AGENT-LOC)

Status: Build. Card answered 28 Oct 19:25. Track: M (no migration, no permission change; reviewer, no
security-reviewer).

## Owner rulings

- 28 Oct ~19:00: "i want to comment on quotation, i think to check stock right, should base on the
  location group of the sales agent of the user, simple as that, cannot simply let them check other
  locations"
- 28 Oct ~19:10: "if a user with no linked agent then cannot see stock, if got several agent then can
  see combination of different groups, certain permission can see the stocks, actually should depend
  on the location allowed for this contact la, that's the source of truth"
- 28 Oct ~19:25: "Q1 based on contact's stock visibility, Q2 no one, purely based on contact's allowed
  location, Q3 quotation screen only first, Q4 a, need to be careful if a contact didn't set any
  allowed locations mean it is allow all, unless it is configured to exclude all location"

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

## Rule (owner rulings applied)

Same for every user, admins included (Q2: no bypass; `resolve_policy` has no role check):
1. No linked ACTIVE agent (`agents_for_contact` on `users.respond_contact_id`) -> no stock, blank.
2. Otherwise the location set = `scope_warehouse_ids(resolve_policy(contact))`: contact override >
   access types > global default (`stock_visibility.py:229`). No row anywhere = all
   (`default_policy` `:121-135` returns `warehouse_ids=None`). Only an empty include list or an
   exclusion covering every active warehouse gives none -> blank.
3. Intersected with active `fulfilment_planning` warehouses: the universe the old picker drew from.
4. The agent's `location_group` plays no part (Q1 (a)); several agents change nothing.

## Design

- BE: `GET /api/v1/project-sales/quotation-line-stock?product_id=` in
  `app/api/v1/projects/quotations.py` (READ pair, like `/quotation-line-images` `:390`). Returns
  `StockDetail` over the set, or `null`. Set computation in one small service function; the read
  reuses `FulfilmentBoardService._stock_detail` via a new `warehouse_ids` seam (see Seams).
- FE: picker and its localStorage removed; `QuotationStockChip`, the popover and the set-part probes
  read the new endpoint through `fulfilmentPlanningService` -> a hook; `null` renders nothing; the
  popover shows the read's rows (all-zero rows dropped), AutoCount restates them without appending
  other locations (`withAutoCount` option), no `pools` read.
- Untouched (Q3 (b)): `fulfilment-planning/stock-detail`, `inventory/stock-status`, the board.

## Slices

One lane, one slice S1 (BE route + FE swap). Tester red tests from the UAC first, then coder.

## Seams (mapped 28 Oct, read-only)

- `FulfilmentBoardService._stock_detail` (`project_fulfilment_board_service.py:979`) turns `group`
  into `codes = {warehouse_id: code}` at `:1039-1047` via `_set_position` (`:1369-1397`); every later
  read uses `target_ids = list(codes)`. No function takes a warehouse-id list today; the smallest seam
  is a `warehouse_ids` argument building `codes` there, deciding the group-keyed branches at `:1031`,
  `:1244`, `:1302`, `:1320`, `:1335`.
- `stock_visibility.scope_warehouse_ids` (`:394`) returns None (all) or the explicit active ids
  (an exclude list expanded); `warehouse_criterion` (`:364`) is the SQL form.
- `GET /inventory/stock-status` (`app/api/v1/inventory/stock_status.py:46`) has no warehouse filter;
  `stock_status_service.py:117-121` reads every warehouse, the natural filter point.
- No caller applies a Stock visibility policy to a staff user today; all resolve it from a request
  `contact_id` (e.g. `inventory_service.py:735`, `purchase_orders.py:174`).

## Next

Red tests (tester), coder, kill test, reviewer, agent-browser 1280/375 on the crew copy, hand-test
script (agent + restricted contact, agent + unset contact, contact excluding all, no agent).
