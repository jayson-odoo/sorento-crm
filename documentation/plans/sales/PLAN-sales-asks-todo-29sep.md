# PLAN: sales asks as a salesperson's to-do list, date-first (lane SALES-ASKS-TODO)

Status: Phase 1 FE mock built and browser-verified 29 Sep 2026 (section 7b); grill posted on PR #1364 (crew-ask, 8 questions), Q6 ruled; the plan is written
under the recommendations and each pending question is marked `[Q<n> pending]` where its answer
changes the design. Track: full (one migration, two new routes under RBAC, one portal route).
Plan created: 2026-09-29T08:20:00Z
Domain: sales (the salesperson's own surface). The rows are CORE (`stock_asks` in `public`, from
#1333); the CRM page rides on the `sales` module menu, the portal page on the existing
`customer_asks` landing kind.
UAC: `sales-asks-todo-29sep-acceptance-criteria.md` (same folder).
Builds on: PR #1333 (stock ask v2 S5 asks table + CRM Asks tab, S6 portal Customer asks), merged
to main 29 Sep 2026 (f4f70531); branch `crew/sales-asks-todo` is on origin/main from that commit.
Sibling: lane CONTACT-CUSTOMERS (contact <-> customers, agent -> customers), PR #1366. Crew ruling
29 Sep 2026 (Q6, coordination): build on `customers.sales_agent_id` now behind the one
`_agent_scope` function; swap to #1366's relation when it lands. Section 4.
Main note (29 Sep 2026): origin/main f4f70531 carries TWO alembic heads,
`chatbot_picker_domain_1352` (#1353) and `sa2_0005_stock_ask_source` (#1333), both chained on
`cpc4_cost_packaging_method`. Crew ruling (29 Sep 2026): lane ALEMBIC-JOIN adds the merge revision
`merge_29sep_batch6`; this lane adds no join of its own. `sat_0001_stock_ask_done` chains on
`sa2_0005_stock_ask_source` until that join merges, then re-chains onto `merge_29sep_batch6`
(`./scripts/alembic-reparent.sh`); a red "Single alembic head" gate until then is expected.

## 0. Owner words (29 Sep 2026, follow-up from PR #1333, verbatim and binding)

> "I think now we got the sales ask, good, but I need it to be more of a to-do list, like the
> salesperson can come in, see oh today my customer ask so many things, let me clear them off
> 1 by 1, so date is very important, I can know which one needs my attention, it is a list that
> requires my attention, basically this needs to be a sales tool for salesperson to see what
> their customer is asking."

Read as five requirements: (R1) the salesperson's own list, of their customers' asks; (R2)
date-first: what came in today, and what has been waiting; (R3) clear off one by one: one action
per row, the row leaves the list; (R4) counts of what is open and what needs attention; (R5) quick
to scan on a phone and on a desktop.

## 1. Journey

Actor: a salesperson (a `sales_agents` row) whose WhatsApp contact is linked to that agent
(`sales_agents.contact_id`). They arrive from the WhatsApp message S4 sent them ("Stock ask -
Hock Lee Trading asked about SRT5674 ...") or from habit, first thing in the morning.

1. **Arrive.** They open the portal (`/portal/c/<slug>` -> Customer asks tab) or, when they hold
   a CRM user linked to the same contact, Sales > My customer asks. The system already knows who
   they are (portal token -> contact -> agent; CRM user -> `users.respond_contact_id` -> agent),
   which customers are theirs (`customers.sales_agent_id`), and every ask the chatbot answered for
   those customers (`stock_asks`). Nothing is asked of them.
2. **See the day.** The first screen is the counts line, `Open 7 · Needs attention 2 · Done
   today 3`, then the groups: `Needs attention` (open, asked before today, oldest first) pinned at
   the top, then `Today` (newest first), then `Yesterday`, then one group per earlier day only
   when it still has open rows. Each row is one ask: customer, contact, product x quantity, the
   branch badge, the chatbot's answer line, the time asked (with "2 days ago" on the old ones),
   and one `Done` button.
3. **Clear one.** They call the customer, then tap `Done`. The row fades out of its group, the
   counts move (`Open 6 · Done today 4`), and the row appears under `Done today` at the bottom,
   greyed, with `Reopen`. No dialog, no page reload. An optional note stays editable on the row
   before or after (the `note` #1333 already has).
4. **Repeat** until `Open 0`. The empty state reads "Nothing waiting. Asks your customers make on
   WhatsApp land here." with the day's cleared rows still under `Done today`.
5. **Look back (optional).** `Show done` reveals every done ask, newest first, paged, the #1333
   list; nothing else changes.
6. **The office** keeps the customer's Asks tab (#1333 S5) with the same rows: a `done` set on
   either side shows on the other, with who did it and when.
7. **The sales admin / owner** opens Sales > Customer asks: every agent's list in the same shape,
   an Agent filter and open / needs-attention counts per agent. `[Q7 pending]`

What the actor never decides: which customers are theirs, what "overdue" means, what order the
rows come in, whether a `Done` needs a reason.

## 2. What exists today (measured on the lane branch, #1333 merged in; file:line)

- `stock_asks` (`sorento_crm_backend/app/models/stock_ask.py:39-69`): customer, contact,
  product, quantity, branch, `answer_summary`, `notified_agent` + `notify_skip_reason`, `state`
  (`open | done`, :63), `note`, `source`, `created_at`, `updated_at`. No `done_at`, no "done by".
- Agent scope: `_agent_scope` (`app/services/stock_ask_service.py:588-596`) =
  `customers.sales_agent_id == agent.id`. Agent from a portal contact: `sales_agent_for_contact`
  (`app/services/price_tag_request_service.py:109`) -> `app/services/sales/portal_agent.py:19`.
- Lists: `_page` (`stock_ask_service.py:525-535`) newest first, paged; `list_for_agent`
  (:599-634) with `q` and `state`; `update_for_agent` (:637-644) and `_apply_update` (:538-546)
  set state and note. CRM: `list_for_customer` / `update_for_customer` (:559-585).
- Routes: portal `GET/PATCH /api/v1/public/portal/customer-asks[/{id}]`
  (`app/api/v1/public/portal_customer_asks.py:53-75`, gate `_agent_id` :37-51: linked agent AND
  the per-contact `customer_asks` switch); CRM `GET/PATCH
  /api/v1/order-management/customers/{id}/asks[/{ask_id}]`
  (`app/api/v1/order_management/customers.py:145-172`).
- Serializer: `serialize` (`stock_ask_service.py:471-522`), names never ids; schema
  `StockAskResponse` / `StockAskUpdate` (`app/schemas/stock_ask.py:10-34`).
- Portal FE: `customer_asks` landing kind; `PortalLanding.tsx:383-387` reads the open count for
  the badge (`limit=1, state=open`), :667-668 renders `CustomerAsksList` as the tab body
  (`app/(auth)/portal/components/CustomerAsksList.tsx:44-295`, cards or grid, State filter);
  cells `components/stock-asks/AskEditCells.tsx:15-103`; words `lib/stock-asks.ts`.
- CRM FE: `CustomerAsksTab.tsx` (DataGrid), `services/stockAskService.ts`, hooks
  `useCustomerAsks.ts`.
- CRM user -> salesperson: `users.respond_contact_id` (`app/models/user.py:72`) ->
  `sales_agents.contact_id` (`app/models/sales_agent.py:96`). No "agent for user" helper exists;
  `app/api/v1/sales/analysis.py:348` does the reverse join by raw SQL.
- Sales module: menu `config/menu.config.tsx:78-118` (Targets, Opportunities, Sales Teams, Sales
  Agents, Yearly comparison; `moduleKey: 'sales'`); permissions `_crud("sales", ...)`
  (`app/rbac/permission_registry.py:829-834`); routes `app/api/v1/sales/*.py`.
- To-do precedent in the CRM: `project-sales/my-tasks/components/MyTasksClient.tsx:14-20`
  (bucketed by urgency, `PageHeader`, one row per task).
- Malaysia wall clock: BE `_MALAYSIA` (`stock_ask_service.py:40`, `asked_at_label` :51); FE
  `formatDateTimeInMalaysia`, `formatDateInMalaysia` (`lib/helpers.ts:330, 451`).

## 3. Design

### 3.1 The rows: two columns on `stock_asks` (migration `sat_0001_stock_ask_done`)

```
stock_asks
  done_at   TIMESTAMP NULL      when state last became done (naive UTC, like created_at)
  done_by   VARCHAR(150) NULL   who set it: the portal contact's name or the CRM user's name
```

Set in ONE place, `_apply_update` (`stock_ask_service.py:538`): a transition to `done` stamps
`done_at = now()` and `done_by = <actor label>`; a transition to `open` clears both; a `note`-only
PATCH touches neither. Every existing route (portal cells, CRM Asks tab, the new to-do buttons)
goes through it, so the office and the agent always see the same "Done by Sean, 29/09/2026
14:02". `done_by` is a name snapshot, not an id: the reader is a human, the row never needs to
join back, and a portal contact and a CRM user are two different tables (one text column beats
two nullable FKs for a label). Trigger for ids: an audit question "which user" that a name cannot
answer. Backfill: rows already `done` get `done_at = updated_at`, `done_by = NULL` (shown as
"Done", no name). `[Q2 pending: (b) adds a `contacted` state to the CHECK; (c) makes the note
required on done]`

`StockAskResponse` gains `done_at`, `done_by` (asserted in a test: `response_model` drops
undeclared fields).

### 3.2 The to-do read: one payload, grouped on the client from one server boundary

`GET /api/v1/public/portal/customer-asks/todo` (portal, same gate as the list) and
`GET /api/v1/sales/customer-asks/todo` (CRM, section 3.4) return the same shape:

```
{
  "today_start": "2026-09-28T16:00:00Z",   Malaysia midnight of today, as UTC
  "open":       [StockAskResponse, ...],   state open, branch in (too_big, in_stock, no_incoming),
                                           oldest first, cap 500, `truncated: bool`
  "done_today": [StockAskResponse, ...],   state done, done_at >= today_start, newest first
  "truncated":  false
}
```

`service.todo_for_agent(db, agent_id, now)`: the same `_agent_scope` as #1333, the branch
filter (`[Q5 pending: (a) drops the branch filter; (c) writes incoming rows done at creation]`),
`today_start` computed once from `_MALAYSIA` (the server owns the day boundary; the FE never
guesses a timezone). No paging: a salesperson's open asks are tens, and a to-do list with a
"next page" is not a to-do list; the cap and `truncated` flag are the guard, shown as "Showing
the oldest 500 open asks".

FE `lib/stock-asks-todo.ts`: `bucketTodo(payload)` (pure, unit-tested) -> `{ counts: { open,
needs_attention, done_today }, groups: [{ key, label, asks }] }` where `needs_attention` = open
and `created_at < today_start` (`[Q4 pending: (b) uses today_start minus one day; (c) reads a
settings value]`), `today` = open and `>= today_start`, older groups keyed by the Malaysia date
(`formatDateInMalaysia`) and labelled `Yesterday` or `Mon 22 Sep`. Rows inside `Needs attention`
oldest first, inside every other group newest first. One rule, one function, both mounts.

### 3.3 The to-do surface: one component, two mounts

`components/stock-asks/AskTodoList.tsx` (shared, like `AskEditCells`): props `{ payload,
loading, error, onDone(askId), onReopen(askId), onNote(askId, note), showAgent?: boolean }`.

- Counts line at the top: `Open N · Needs attention M · Done today K` (plain text with the
  numbers in `tabular-nums`; the M turns `text-destructive` when > 0).
- Groups as headed sections (`Needs attention`, `Today`, `Yesterday`, dates), each a `<ul>` of
  rows. A row: line 1 customer name (bold) and the contact name; line 2 `SRT5674 x 50` and the
  branch `Badge`; line 3 the answer summary (truncate + title); line 4 the time asked
  (`formatDateTimeInMalaysia`) with the age ("2 days ago") on `Needs attention` rows, the
  `Console` badge on console rows, and the `Notified` badge; right column (or below at 375px):
  `Done` (primary, `size="sm"`) and the note input from `AskEditCells`. `showAgent` adds the
  agent code on line 1 (CRM manager page).
- `Done today` section at the bottom: the same rows greyed (`opacity-60`), `Done by <name>
  <time>`, `Reopen` (outline). Empty when none.
- Empty state (no open, no done today): icon, "Nothing waiting", hint "Asks your customers make
  on WhatsApp land here." No button (one CTA per page rule; there is no CTA here at all: asks
  come from the chatbot).
- `Show done` (a `Button variant="ghost"` at the foot) toggles the #1333 list (`CustomerAsksList`
  in list view with `state=done`) under the to-do, so history stays one tap away and the to-do
  stays a to-do.
- Motion: a done row leaves with `motion.ts`'s fade preset (reduced-motion: none); nothing else
  animates. No skeleton pulse beyond the existing `Skeleton`.
- 375px: one column, buttons full width under the row text; 1280px: row text left, actions
  right (`sm:grid-cols-[1fr_auto]`). No horizontal scroll, no DataGrid (a to-do is not a grid).

Portal mount: `CustomerAsksList` becomes the to-do (`AskTodoList` fed by
`customer-asks-service.ts` -> `/customer-asks/todo`), the State filter and cards/list toggle go
(the to-do has its own sections; `Show done` replaces the filter). The landing badge keeps
reading the open count. `[Q1 pending: (a) is this mount alone; (b) is the CRM mount alone with
the portal untouched]`

CRM mount: `app/(protected)/sales/customer-asks/page.tsx` -> `MyCustomerAsksClient` with
`PageHeader` title "Customer asks", the same `AskTodoList`. Menu entry Sales > Customer asks
(`moduleKey: 'sales'`, permission `sales.customer_asks.view`). Hooks `useCustomerAsksTodoQuery`
/ `useAskDoneMutation` (invalidate + toast) over `services/stockAskService.ts` ->
`/api/v1/sales/customer-asks/todo` and `PATCH /api/v1/sales/customer-asks/{id}`.

### 3.4 CRM routes and scope (`app/api/v1/sales/customer_asks.py`)

- `GET /api/v1/sales/customer-asks/todo?agent_id=` and `PATCH
  /api/v1/sales/customer-asks/{ask_id}` `{state, note}`, both under `sales.customer_asks.view`
  (`_crud("sales", "customer_asks", "Customer Asks")`, `.edit` gates the PATCH), migration
  grants `.view` + `.edit` to every role holding `sales.opportunities.view` and to `admin`
  (the `sales_0003_opportunities` sweep shape), integration roles excluded.
- "Me": `agent_for_user(db, user)` (new, `app/services/sales/portal_agent.py`, beside
  `agent_for_contact`): `users.respond_contact_id` -> `agent_for_contact`. Without `agent_id`
  the list is mine; a user linked to no agent gets `{open: [], done_today: [], ...,
  agent: null}` and the page shows "You are not linked to a sales agent" (no 403: the page is
  still theirs to open).
- `agent_id` given (the manager filter): allowed with `sales.customer_asks.view_all`
  (one extra slug, registered beside the `_crud` four, granted with them); without it 403.
  `[Q7 pending: (a) drops `agent_id`, `view_all` and the manager page; (c) adds a team-leader
  branch: `agent_id` must be a current member of a team the caller's agent leads]`
- PATCH scope: the ask's customer's agent is mine, or I hold `view_all` (the office marking on
  an agent's behalf); otherwise 404, never 403 (no id probing). Actor label for `done_by`: the
  user's full name.

Manager page: the same `page.tsx` with an `Agent` `SearchableSelect` (clearable, options from
`services/salesAgentService` with open counts fetched from
`GET /api/v1/sales/customer-asks/agents` -> `[{agent_id, code, name, open, needs_attention}]`)
shown only with `view_all`; `showAgent` on the list when an agent other than mine, or all, is
chosen. `[Q7 pending]`

### 3.5 Portal route

`GET /api/v1/public/portal/customer-asks/todo` in `portal_customer_asks.py`, same `_agent_id`
gate, `todo_for_agent`. PATCH stays the #1333 one (`update_for_agent`), now stamping `done_by`
with the contact's label (`_contact_label`). Nothing else on the portal changes.

## 4. Coordination with CONTACT-CUSTOMERS

Every read in this lane goes through `_agent_scope(db, agent_id)` (`stock_ask_service.py:588`).
When that lane lands its agent -> customers relation, this function's `filter` is the one line
that changes; the to-do, the counts, the CRM page and the portal page all follow. Nothing here
adds a second copy of "whose customers", and no schema for the relation is added here.
Ruled (crew, 29 Sep 2026): (a), build on `customers.sales_agent_id` now; swap when PR #1366 lands.

## 5. Simplest thing, not built (and the trigger that would build it)

- No digest or reminder: S4's per-ask WhatsApp stays the nudge. Trigger: the owner asks for a
  morning "you have N open" after using the list. `[Q8]`
- No middle state, no assignment, no due date, no snooze. Trigger: a salesperson asks to park an
  ask. `[Q2]`
- No settings row for the overdue rule. Trigger: a second threshold is asked for. `[Q4]`
- No team-leader scoping. Trigger: a leader asks to see only their team. `[Q7]`
- No paging on the to-do (cap 500 + flag). Trigger: an agent whose open asks exceed the cap.
- No new table: two columns on the row that exists. No registry for the day buckets: one pure
  function.

## 6. Slices

### S1: done stamps + the to-do payload + the portal to-do (the owner's ask)

Migration `sat_0001_stock_ask_done` (`ADD COLUMN IF NOT EXISTS` x2, backfill done rows,
re-parented onto main's head at PR time; chains on `sa2_0005_stock_ask_source` until #1333
merges). Backend: `_apply_update` stamps, `todo_for_agent`, `StockAskResponse` fields, portal
`todo` route. Frontend: `bucketTodo`, `AskTodoList`, the portal mount, the landing badge
unchanged. Tests: section 7, AC-ST101 to AC-ST118.

### S2: the CRM mount, mine and (with `view_all`) every agent

Permissions + grant sweep in the same migration file as S1 (one migration for the lane), routes
`app/api/v1/sales/customer_asks.py`, `agent_for_user`, menu entry, page, hooks, service. Tests:
AC-ST201 to AC-ST214.

Phase order per `/feature`: Phase 1 FE mock (both mounts, mocked service, 375 and 1280, agent-
browser evidence) -> crew-handtest -> Phase 2 tester-first (red pytest + vitest) -> coder ->
Phase 3 reviewer + security-reviewer (portal ingest and RBAC are touched, so it runs) + browser
verification.

## 7. Tests (tester first; the captain's list is in the UAC, one line per AC)

pytest (Postgres, `tests/_pg_fixture.py`, every test seeds its own agent, contact, customers,
asks): `tests/test_stock_ask_todo.py` (service: scope, branch filter, ordering, cap, today_start,
done stamps and clears, backfill), `tests/test_portal_customer_asks_todo.py` (route: gate, shape,
PATCH stamps `done_by` with the contact label), `tests/test_sales_customer_asks_api.py` (CRM:
mine via `respond_contact_id`, unlinked user, `agent_id` without `view_all` 403, PATCH out of
scope 404, permission grants), `tests/test_migration_sat_0001.py` (columns, backfill, grants).
vitest: `lib/stock-asks-todo.test.ts` (bucket table), `AskTodoList.test.tsx` (counts, groups,
Done moves a row, Reopen, empty state, `showAgent`), `CustomerAsksList.test.tsx` rewritten for
the to-do body, `MyCustomerAsksClient.test.tsx`, `menu.config` test for the entry.

## 7b. Phase 1 evidence run (29 Sep 2026, agent-browser, sandbox dev server, mock store)

Deviation recorded: the coder ran in the lane checkout, not a worktree (a cloud sandbox with no
concurrent editor). Sandbox-only seeds, never committed: every catalog module enabled for the
default tenant, the five `sales.customer_asks.*` slugs inserted so superadmin's permission list
carries them (Phase 2's migration is what adds them for real).

- CRM, 1280x800: signed in as a superadmin, sidebar Sales group -> `Customer asks` listed after
  Opportunities -> `/sales/customer-asks`. `PageHeader` "Customer asks", Agent select (view_all),
  counts `Open 5 · Needs attention 2 · Done today 1`, groups `Needs attention` (2 rows, oldest
  first, red age labels "2 days ago" / "Yesterday") and `Today` (3 rows, one with the Console
  badge). `Done` on the oldest row: counts `Open 4 · Needs attention 1 · Done today 2`, the row
  under `Done today` reading "Done by Sean Ibrahim 29/09/2026, 3:43 pm" with `Reopen`. Console:
  no error; `errors`: none.
- CRM, 375x812: `scrollWidth == clientWidth` (360), one column, `Done` full width under the row
  text. `Reopen` restores `Open 5 · Needs attention 2 · Done today 1`.
- Portal, 375x812: `/portal/c/sean` with a verified token planted in local storage; the landing
  selector lists `Customer asks 6` (the #1333 badge, one higher than the to-do's Open because the
  mock list still counts the `incoming` ask; Q5 decides); picking it renders the same counts and
  groups as the CRM. `Show done` opens the #1333 grid under the to-do (`state=done`, 1 row) and
  reads `Hide done` while open. No page errors.
- Portal, 1280x800: two-column rows, actions right; the done row greyed with its note.
- Coder's Phase 1 divergences, standing for Phase 2 unless the grill moves them: one flat
  `Needs attention` group (oldest first, age label per row) instead of per-day groups, because
  a row cannot sit in both a pinned aging group and its day group (AC-ST113's day labels are
  kept as `dayLabel`); `agent_id=all` added to the CRM todo contract for the manager's "All
  agents" choice (AC-ST210); the portal search filters the to-do client-side.
- Vitest breakage to hand the tester: `CustomerAsksList.test.tsx` (10, pins the replaced body),
  `PortalLanding.customerAsks.test.tsx` (2, the body and the server-side search),
  `menu.config.sales.test.ts` (2, the new entry).

## 8. Risks

- #1333 not merged: this branch carries its 33 commits; a #1333 fix round changes files this lane
  edits (`stock_ask_service.py`, `CustomerAsksList.tsx`). Mitigation: merge #1333's head into
  this branch on every crew notice, and keep this lane's edits additive (new functions, new
  component) where it can.
- The migration chains on `sa2_0005_stock_ask_source`; if #1333 is re-parented before merge, this
  one re-parents with `./scripts/alembic-reparent.sh`.
- `CustomerAsksList.test.tsx` and `PortalLanding.customerAsks.test.tsx` from #1333 pin the cards /
  grid body; S1 rewrites the first and keeps the second green (the badge and kind are unchanged).
