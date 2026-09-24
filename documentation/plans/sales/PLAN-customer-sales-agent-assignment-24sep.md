# PLAN: assign a sales agent to a customer from the CRM (sales module slice 1)

Status: small fix track, PR open (#1177). Issue #1170 slice 1; unblocks #1168.
Domain: sales (customer master, order_management module).
UAC: `customer-sales-agent-assignment-24sep-acceptance-criteria.md` alongside.

## Measured facts (origin/main 319f4226)

- `customers.sales_agent_id` FK to `sales_agents.id` ON DELETE SET NULL already exists (`app/models/order.py:142`). Set only by import and document ingest today; read by the portal debtor dropdown (`price_tag_request_service.py:2408`).
- `sales_agents` master (`app/models/sales_agent.py:42`) has `sales_agent` (code), `person_label`, `contact_id` (WhatsApp contact, picker already on the sales agent form at `/master-data-management/sales-agents/[id]`). Sales agents are NOT users and NOT a role (ruling 14 Aug 2026 in the module docstring). Frontend service `services/salesAgentService.ts` and `hooks/useSalesAgents.ts` exist under that page.
- `CustomerResponse` / `CustomerUpdate` in `app/schemas/order.py:44-70` are thin and do not carry `sales_agent_id`. `customer.types.ts:22,46` has no `sales_agent_id`. `CustomerForm.tsx` (260 lines) and `CustomerDetail.tsx` (144 lines) under `app/(protected)/order-management/customers/[id]/` render no agent field. Coder: confirm whether the customers GET/list path returns a pydantic model or a manual dict (lesson: a column must be added to every manual dict builder, and `response_model` drops undeclared fields).

## Model (owner-confirmed 24 Sep 2026)

Customer (dealer) has one sales agent. Sales agent has one WhatsApp contact. Notifications later flow customer -> agent -> contact. No new table, no migration.

## Change (one seam)

1. Backend: `sales_agent_id: UUID | None` on `CustomerUpdate` and `CustomerCreate` if it exists; `sales_agent_id`, `sales_agent_code`, `sales_agent_name` (person_label) on `CustomerResponse` and on the list serializer registered in `list_query_registry.py` for customers. Validation: the agent must exist and be visible under company scope; 422 otherwise. Permission: `order_management.customers.edit` / `.add` exist in the registry but the PUT/POST customer routes do not enforce them today (review PR #1177 round 1, security item 2) - gating them is an auth change, out of scope for this small-fix lane, tracked as a follow-up in #1190.
2. Frontend: `sales_agent_id` + display names on `Customer` / `CustomerFormData` types; `SearchableSelect` "Sales agent", clearable, options from the sales agent service (search by code and name, no capped dropdown: reuse the existing sales agents select pattern or a `useSalesAgentsSelect` that queries by term); read-only value on `CustomerDetail` in the same position as the form (view = edit layout); a "Sales agent" column on the customers DataGrid with explicit `size`, truncate + title.
3. No UUID visible anywhere: show `code - name`.

## Tests (tester-first)

- pytest: PATCH customer with a valid agent persists and the GET returns id + code + name; unknown agent 422; clearing to null persists; list endpoint carries the agent columns; company scope: an agent from another company is rejected.
- vitest: CustomerForm renders the select with the current agent preselected, clear sets null in the payload, CustomerDetail shows `code - name` and an empty state when unset.
- Browser (agent-browser, sidebar navigation from `/`): set an agent on a customer, reload, value persists; clear it; column visible on the list at 1280 and usable at 375.

## Out of scope

Notification triggers, the asks log, targets (later slices of #1170 and #1168).
