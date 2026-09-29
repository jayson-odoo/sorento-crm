# UAC: sales asks as a salesperson's to-do list, date-first (lane SALES-ASKS-TODO)

Status: draft under the grill recommendations (PR #1364 crew-ask, 29 Sep 2026); ACs marked
`[Q<n>]` move with that question's ruling. Plan: `PLAN-sales-asks-todo-29sep.md`.
Numbering: AC-ST<slice><nn>. Tags: [BE] pytest (Postgres), [FE] vitest, [E2E] recorded
agent-browser evidence, [T] a test that pins a rule, [UX] a measurable design AC. The `tester`
writes every [BE]/[FE] test red before the `coder` starts the slice.

## Journey

Actor: a salesperson whose WhatsApp contact is linked to a `sales_agents` row. The system knows
who they are (portal token -> contact -> agent, or CRM user -> `users.respond_contact_id` ->
agent), which customers are theirs (`customers.sales_agent_id`), and every ask the chatbot
answered for those customers (`stock_asks`, PR #1333).

1. **Arrive** at the portal Customer asks tab, or Sales > Customer asks in the CRM.
2. **See the day**: `Open N · Needs attention M · Done today K`, then `Needs attention` (open,
   asked before today Malaysia time, oldest first), `Today`, `Yesterday`, earlier days.
3. **Clear one**: tap `Done`; the row moves to `Done today` with who and when; counts move.
4. **Repeat** to `Open 0`; the empty state says nothing is waiting.
5. **Look back**: `Show done` reveals the full done history (the #1333 list).
6. **The office** sees the same state, `done_by` and `done_at` on the customer's Asks tab.
7. **The sales admin** sees every agent's list with an Agent filter and per-agent counts. [Q7]

## S1: done stamps, the to-do payload, the portal to-do

Fixture for every S1 test: agent A (contact CA), agent B (contact CB), customers X and Y assigned
to A, customer Z assigned to B, asks with `created_at` set explicitly around a fixed `now`
(`2026-09-29T03:00:00Z`, i.e. 11:00 Malaysia; `today_start = 2026-09-28T16:00:00Z`).

- **AC-ST101 [BE]** After `sat_0001_stock_ask_done`, `stock_asks` has `done_at TIMESTAMP NULL`,
  `done_by_user_id VARCHAR NULL` (FK `users.id` ON DELETE SET NULL) and `done_by_contact_id TEXT
  NULL` (FK `respond_contacts.id` ON DELETE SET NULL); re-running the migration is a no-op.
  (Audit actor contract, identity plan 8.3: ids, never a name.)
- **AC-ST102 [BE]** Backfill: a row already `done` before the migration reads `done_at =
  updated_at` with both actor ids NULL; an `open` row reads all three NULL.
- **AC-ST103 [BE][T]** `_apply_update(..., actor_user_id=, actor_contact_id=, now=)` with
  `{state: done}` sets `done_at = now` and the actor ids as given; a second `{state: done}` on a
  done row leaves all three as they were; `{state: open}` clears all three; `{note: "x"}` alone
  changes none. Applies through the portal PATCH (`actor_contact_id` = the token's contact, plus
  `actor_user_id` when a user is linked to that contact) and the CRM customers PATCH
  (`actor_user_id` = the current user).
- **AC-ST104 [BE]** `StockAskResponse` carries `done_at` and `done_by`, the LABEL `serialize`
  resolves (the user's `name` when `done_by_user_id` is set, else the contact label, else None);
  no actor id is on the wire. Asserted field by field on the portal list, the CRM customers list
  and the to-do payload.
- **AC-ST105 [BE]** `todo_for_agent(A, now)`: `open` holds only asks of X and Y with `state =
  open`; Z's asks and customer-less asks are absent.
- **AC-ST106 [BE]** `open` holds branches `too_big`, `in_stock`, `no_incoming` only; an open
  `incoming` ask is absent from `open` and does not count. [Q5]
- **AC-ST107 [BE]** `open` is ordered by `created_at` ascending, id as tie-break; `done_today` by
  `done_at` descending.
- **AC-ST108 [BE]** `today_start` in the payload is Malaysia midnight of `now` expressed in UTC
  (`2026-09-28T16:00:00Z` for the fixture `now`); at `now = 2026-09-28T15:59:00Z` it is
  `2026-09-27T16:00:00Z`.
- **AC-ST109 [BE]** `done_today` holds asks with `done_at >= today_start` only; one done at
  `today_start - 1s` is absent; one reopened (state open, `done_at` NULL) is absent.
- **AC-ST110 [BE]** With 501 open asks the payload holds the oldest 500 and `truncated = true`;
  with 500 it holds all and `truncated = false`.
- **AC-ST111 [BE]** `GET /api/v1/public/portal/customer-asks/todo` as CA (switch on) returns
  AC-ST105's payload; as a contact with no agent 403 `NOT_A_SALES_AGENT`; as CA with the
  `customer_asks` switch off 403 `FORM_TYPE_NOT_VISIBLE`.
- **AC-ST112 [BE]** `PATCH /api/v1/public/portal/customer-asks/{id}` `{state: done}` as CA on X's
  ask stamps `done_by_contact_id = CA` (and `done_by_user_id` = the user linked to CA when one
  exists), returns `done_by` = CA's contact label and a `done_at`; the same on Z's ask is 404.
- **AC-ST113 [FE][T]** `bucketTodo(payload)` with `today_start = 2026-09-28T16:00Z`: an open ask
  at `2026-09-28T15:59Z` is in `Needs attention`; one at `2026-09-28T16:00Z` is in `Today`; one at
  `2026-09-27T20:00Z` is in `Needs attention` and its group label for the day list is
  `Yesterday`; one at `2026-09-22T05:00Z` shows `Tue 22 Sep`; counts read `{open: 4,
  needs_attention: 3, done_today: <len done_today>}`. `Needs attention` rows are oldest first;
  `Today` rows newest first. [Q3][Q4]
- **AC-ST114 [FE]** `AskTodoList` renders the counts line, the group headings in order (`Needs
  attention`, `Today`, `Yesterday`, dates), one row per ask with customer, contact, `CODE x Q`,
  branch badge, answer line, time asked, and a `Done` button; `Needs attention` rows carry an
  age label ("2 days ago") and the count in the header is `text-destructive` when > 0.
- **AC-ST115 [FE]** Clicking `Done` calls `onDone(askId)`; after the payload refetch the row
  renders under `Done today` greyed with `Done by <name> <time>` and a `Reopen` button that calls
  `onReopen(askId)`; the note input saves through `onNote` on blur (the `AskEditCells` cell).
- **AC-ST116 [FE]** Empty payload renders "Nothing waiting" with the hint and no button; a payload
  with `truncated = true` renders "Showing the oldest 500 open asks".
- **AC-ST117 [FE]** Portal: the `customer_asks` tab body is `AskTodoList` fed by
  `/customer-asks/todo`; `Show done` toggles the #1333 done list (`state=done`) under it; the
  landing badge still reads the open count (`PortalLanding.customerAsks.test.tsx` stays green).
  [Q1]
- **AC-ST118 [E2E]** Portal as CA on the seeded fixture: counts read `Open 3 · Needs attention 2
  · Done today 0`; tap `Done` on the oldest: it appears under `Done today` with CA's name, counts
  read `Open 2 · Needs attention 1 · Done today 1`; reload: persisted; the CRM customer X Asks tab
  shows the row `Done` with the same name. 375px: one column, `Done` reachable without horizontal
  scroll; 1280px: actions on the right. Recorded agent-browser evidence.
- **AC-ST119 [UX]** The done row leaves its group with the `motion.ts` fade preset (under 200 ms)
  and renders instantly under `prefers-reduced-motion`; nothing else on the page animates;
  `Done` shows the pressed state token.

## S2: the CRM mount, mine and every agent

- **AC-ST201 [BE]** `user_permissions` holds `sales.customer_asks.{view,add,edit,delete}` and
  `sales.customer_asks.view_all`; every role holding `sales.opportunities.view` and `admin` hold
  `.view`, `.edit` and `.view_all`; an `integration_*` role holds none. [Q7]
- **AC-ST202 [BE][T]** `agent_for_user(db, user)`: a user whose `respond_contact_id` is CA
  resolves agent A; a user with no contact, or a contact linked to no agent, resolves None.
- **AC-ST203 [BE]** `GET /api/v1/sales/customer-asks/todo` as the A-linked user returns AC-ST105's
  payload plus `agent: {code, name}`; as an unlinked user returns empty arrays and `agent: null`
  (200, not 403); without `sales.customer_asks.view` 403.
- **AC-ST204 [BE]** `GET .../todo?agent_id=<B>` with `view_all` returns B's payload; without
  `view_all` 403; an unknown agent id 404. [Q7]
- **AC-ST205 [BE]** `GET /api/v1/sales/customer-asks/agents` with `view_all` lists every agent
  that has at least one open ask with `{agent_id, code, name, open, needs_attention}` computed
  with the same rules as the payload; without `view_all` 403. [Q7]
- **AC-ST206 [BE]** `PATCH /api/v1/sales/customer-asks/{id}` `{state: done}` as the A-linked
  user on X's ask stamps `done_by_user_id` = that user and returns `done_by` = the user's name;
  on Z's ask 404; with `view_all` on Z's
  ask 200; without `.edit` 403; a bad state 422.
- **AC-ST207 [BE]** A user scoped to another company sees none of A's asks (company scope holds
  on the new routes).
- **AC-ST208 [FE]** `config/menu.config.tsx` Sales group has `Customer asks` ->
  `/sales/customer-asks`, `permission: 'sales.customer_asks.view'`, `moduleKey: 'sales'`,
  placed after Opportunities.
- **AC-ST209 [FE]** `/sales/customer-asks` renders `PageHeader` "Customer asks" and
  `AskTodoList` from `useCustomerAsksTodoQuery`; `Done` / `Reopen` go through
  `useAskDoneMutation` (invalidate + toast, `extractApiError`); an unlinked user sees "You are not
  linked to a sales agent" in place of the list.
- **AC-ST210 [FE]** With `view_all`, an `Agent` `SearchableSelect` (clearable) sits in the header
  actions listing agents with their open counts ("SEAN I · 4 open · 2 need attention"); picking
  one refetches with `agent_id`; clearing returns to mine; choosing `All agents` shows every
  agent's rows with the agent code on line 1 (`showAgent`). Without `view_all` no select renders.
  [Q7]
- **AC-ST211 [FE]** `services/stockAskService.ts` exposes `getCustomerAsksTodo`, `listAskAgents`,
  `updateSalesAsk`, all via `apiFetch` + `extractApiError`; no component calls fetch.
- **AC-ST212 [E2E]** Sidebar from `/`: Sales > Customer asks as the A-linked user: the same
  counts and groups as AC-ST118, `Done` on one row moves it, reload persists; as admin the Agent
  select lists A and B with counts, picking B shows Z's asks. 375px and 1280px: no clipping.
- **AC-ST213 [BE][T]** `test_schema_uuid_id_principle.py` passes with no exemption; no response
  carries a bare `sales_agent_id` or `customer_id` beyond the ask's own `id` and `agent_id` in the
  agents list (the filter key, never shown).
- **AC-ST214 [E2E]** The office marks an ask done on customer X's Asks tab: the portal to-do (CA)
  and the CRM to-do show it under `Done today` with the office user's name.
