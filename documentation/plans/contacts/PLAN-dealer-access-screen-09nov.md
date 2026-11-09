# PLAN: Dealer access screen (portal screen on the #2268 grant service)

Status: Build (owner approved mock v3, 9 Nov 23:31, option (a), no admin view). Track: full (access grant surface,
security review). Lane: DEALER-ACCESS-SCREEN. Follow-up of DEALER-ACCESS-PORTAL (#2268, merged 918f3d4d).
UAC: `dealer-access-screen-09nov-acceptance-criteria.md`. Mock: `dealer-access-screen-mock-v3.html`.

## Journey

A salesperson opens MY WORK > Dealer access, sees the people linked to THEIR OWN customers (company as a filter),
adds people to their own accounts (name, phone, Business Owner or Employee), edits a person's accounts or level, or
unlinks a person from one of their accounts. Every write goes through the #2268 service the AI agent uses.

## Chain (owner question 23:25)

user `respond_contact_id` -> active `sales_agents.contact_id` (`portal_agent.agents_for_contact`) -> active customers
with that `sales_agent_id` (`writes._own_agent_ids`) -> `respond_contact_customers` -> contacts. Level = the company's
owner tag. A contact under another salesperson's dealer shows only under my accounts, with "also another account".

## Design (simplest thing that works)

No migration, no new table, no second write path.

Backend
1. `app/services/dealer_access_screen.py`: `my_accounts`, `list_people` (reads only), `grant` (validates every row
   with `contact_grant.plan`, then `contact_grant._execute` per row), `update` (`writes._contact_execute` with
   link / unlink / role diff), `unlink_link` (the deferred action's body, same `_contact_execute`). The user dict
   comes from `app.dependencies._load_user_dict_from_db`, under `company_scope_resolver.grants_scope`.
2. Routes `app/api/v1/sales/dealer_access.py` (mounted in `app/api/v1/sales/__init__.py`), each
   `require_permission("user_management.contacts.edit_own")`.
3. Record action `dealer_access.unlink` in `app/services/record_actions.py`, park-time visibility in
   `app/api/v1/system/pending_actions.py` `_assert_entity_visible`.
4. #2268 minor: `loop._previous_waiting` returns the immediately preceding turn's `batch_typed` even when that turn
   left no row waiting (M1).

Frontend (`app/(protected)/sales/dealer-access/`): page + list + `DealerAccessFormDialog` (add and edit), service
`services/dealerAccessService.ts`, hooks `useDealerAccessQuery` / `useDealerAccessMutations`, menu item MY WORK.
Every element per the mock v3 reuse table.

## Tests (red first)

pytest `tests/test_dealer_access_screen.py`: S1-S7 (two salespeople sharing a dealer across Sorento and Mocha;
leak checks on every response; all-or-nothing grant; edit diff; deferred unlink as requester incl. C4).
`tests/chatbot/agent/test_dealer_access_agent.py`: M1 replay. vitest: form row errors, list empty state, menu item.

## Steps

1. Mock v1 -> v2 -> v3 (done, approved). 2. M1 red-first (done in this lane). 3. Tester red tests, coder, kill
tests, reviewer + security review, browser pass on seeded data, `laneboard/scripts/<PR>.md`.
