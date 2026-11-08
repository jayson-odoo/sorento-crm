# PLAN: Dealer access portal (salesperson self-service dealer user access)

Status: Asked (card + mock v1 wait on owner answers; UAC drafted on the (a) answers). Track: full (new screen, grants
data access, RBAC grant migration, Respond.io create).
Lane: DEALER-ACCESS-PORTAL. Card `CARD-dealer-access-portal-09nov.md`; UAC
`dealer-access-portal-09nov-acceptance-criteria.md`; mock `dealer-access-portal-mock.html`.

## Journey

A salesperson, in the CRM portal, picks one of THEIR customers (per company: Sorento / Mocha), adds 1..n people (name,
phone, access level), submits, and access works at once: the contact exists (Respond side too), is linked to that
customer, carries the right access, and the bot answers that person with the right scope. Replaces the Google Form +
Excel import + manual tag + manual access-sheet link.

## Pipeline map (today)

`CARD-dealer-access-portal-09nov.md` sections 2-3 (file:line).

## Design (simplest thing that works)

No new table. The grant is the existing engine; the only new pieces are a salesperson-scoped surface and a Respond
create.

Backend
1. `app/services/dealer_access_portal.py`:
   - `my_accounts(db, user)`: own agents (`portal_agent.agents_for_contact` of `users.respond_contact_id`), active
     customers with `sales_agent_id` in them, per company, under the user's grants scope.
   - `list_people(db, user, company_id)`: links of those accounts + contact + level + WhatsApp state + linked_by/at.
   - `grant(db, user, company_code, account_ids, people)`: validates every row first (U7, U8, U12), then per row
     calls the engine the way `contact_grant.plan/_execute` does, with `skip = frozenset()` (U10, Q2 a) and the
     picked accounts by id (re-checked as own). Shared helpers are moved out of `contact_grant.py` (one copy), not
     duplicated. One commit; then enqueue the Respond job per new or id-less contact.
   - `remove(...)`, `change_level(...)`: U16-U18, ownership re-checked server side.
2. Routes `app/api/v1/sales/dealer_access.py` (GET accounts, GET people, POST grant, PUT level, unlink as a
   deferred record action `dealer_access.unlink` in `record_actions.py`), all `require_permission(contacts.edit_own)`.
3. `RespondClient.create_contact` (`integration_service.py`) + RQ task `respond_io_tasks.ensure_respond_contact`
   (lookup by phone, create if missing, store id, write `backend_id`); no-op without an API key.
4. Migration: grant `user_management.contacts.edit_own` to role `salesperson`; widen the permission description.
5. Staff-phone check: `users.respond_contact_id` or `sales_agents.contact_id` equals the contact (U8).

Frontend (`app/(protected)/sales/dealer-access/`): page + `DealerAccessGrid` + `AddPeopleDialog` per the mock;
`services/dealerAccessService.ts`, hooks `useDealerAccessQuery` / `useDealerAccessMutations`; menu item in
`config/menu.config.tsx` (audience salesperson).

## Tests (red first, from the UAC)

pytest: U1-U3 scoping (two salespeople, two companies, a shared dealer), U5-U13 grant (new contact, existing contact,
digits match, staff phone, own phone, duplicate in form, all-or-nothing, whole template despite no stock/agent/company
perms, idempotent re-submit, other-account notice names nothing), U14-U15 Respond job with a mocked client and no-key
no-op, U16-U18 remove/level, U19 sheet + agent unchanged (existing suites). vitest: dialog row validation, 375px
layout smoke.

## Open

Owner answers Q1-Q5; crew-data-request rows for the examples; Google Form one-off (separate, after the screen).
