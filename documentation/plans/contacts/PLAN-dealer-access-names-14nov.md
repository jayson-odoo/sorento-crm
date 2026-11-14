# PLAN: Dealer access - customer names on chips; Add people also makes the Respond.io contact

Status: Plan (behaviour card filed as crew-ask, waiting on answers). Track: M, LEAD pattern (external write to
Respond.io, so security-reviewer joins).

Lane: DEALER-ACCESS-NAMES. Follows `PLAN-dealer-access-screen-09nov.md` (#2294) and `PLAN-dealer-access-portal-09nov.md`
(#2268).

## Owner ask (14 Nov)

"actually debtor code is useless for salesperson, we should show the customers name I would say, and can you make sure
creating here also create like a contact in respond and grant access to this contact?"

## Discovery (what the code does today)

1. Chips. `DealerAccessView.tsx:61-69` `AccountPills` builds pills from `row.accounts` with `label: a.code`. The
   people API already returns each account's `name` (`dealer_access_screen.py:144-146`), so the fix is FE only.
   Search matches name or phone or account CODE only (`dealer_access_screen.py:173-178`), not account name.
2. Add people. `DealerAccessFormDialog.tsx:139` -> `grant()` `dealerAccessService.ts:120` -> `POST
   /sales/dealer-access/grant` `dealer_access.py:68` -> `dealer_access_screen.grant` `dealer_access_screen.py:194`,
   which plans every row with the agent's `contact_grant.plan` and then runs `contact_grant._execute`
   (`contact_grant.py:620`). That is the #2268 grant service, one path already.
   - Existing phone: `contact_grant._find_contact` (`contact_grant.py:350`) matches the CRM contact by digits, so it
     LINKS; two contacts with one phone are refused.
   - New phone: a CRM `respond_contacts` row is created (`contact_grant.py:628-641`), access + links + tags applied,
     audit row written, committed.
   - Respond.io: AFTER the commit, `ensure_respond_contact` is ENQUEUED on the `respond_io` worker queue
     (`contact_grant.py:689-698`). The worker looks the phone up in Respond.io and creates it on a 404, then stores
     `respond_io_id` and writes `backend_id` (`respond_io_tasks.py:873-946`).
   - Gaps: the salesperson is told "Access given" before Respond.io is known; a failed job (Respond.io down) or a failed
     enqueue is only a server log line (`contact_grant.py:698`); nothing on the screen says the person is not yet in
     Respond.io and there is no Try again. Respond.io calls are counted (`respond_call_counter.httpx_request_hook`,
     `integration_service.py:384-390`) but these two calls do not write an `integration_logs` row.
3. "also another account". `AccessCell` `DealerAccessView.tsx:39-58` shows it when `row.other_account`, which is
   `bool(writes._not_own_links(...))` (`dealer_access_screen.py:181-186`, `writes.py:1000`): the person is ALSO linked
   to a customer that is not one of this salesperson's own accounts (another salesperson's account, or an inactive
   one). It is never named (privacy rule S3/S8 of the screen plan).

## Reuse map

| Piece | Existing | Decision |
| --- | --- | --- |
| Chip list | `components/common/PillOverflow` | reuse, label = customer name |
| Grant | `dealer_access_screen.grant` -> `contact_grant.plan/_execute` | reuse as is |
| Respond.io find-or-create | `respond_io_tasks.ensure_respond_contact` | reuse; extend with an integration log row |
| Respond.io log | `IntegrationLogService` (`integration_service.py:866`) | reuse |

Rest of the plan follows the crew's answers to the behaviour card.
