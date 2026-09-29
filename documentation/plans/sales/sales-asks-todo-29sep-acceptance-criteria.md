# UAC: sales asks as a salesperson's to-do list, date-first (lane SALES-ASKS-TODO)

Status: owner rulings Q1 to Q8 applied 29 Sep 2026 (plan section 0b) and the Lavish-approved mockup
(plan 0c, round 3) applied as S3 below; where an S1/S2 AC and an S3 AC disagree on what is on
screen, S3 wins (AC-ST114 to 117, 120, 121, 209, 210 are superseded as noted). Plan: `PLAN-sales-asks-todo-29sep.md`.
Numbering: AC-ST<slice><nn>. Tags: [BE] pytest (Postgres), [FE] vitest, [E2E] recorded
agent-browser evidence, [T] a test that pins a rule, [UX] a measurable design AC. The `tester`
writes every [BE]/[FE] test red before the `coder` starts the slice.

## Journey

Actor: a salesperson whose WhatsApp contact is linked to a `sales_agents` row. The system knows
who they are (portal token -> contact -> agent, or CRM user -> `users.respond_contact_id` ->
agent), which customers are theirs (`customers.sales_agent_id`), and every ask the chatbot
answered for those customers (`stock_asks`, PR #1333).

1. **Arrive** at the portal Customer asks tab, or Sales > Customer asks in the CRM.
2. **See the day**: `Open N · Needs attention M · Done today K` and the Sort select, then `Needs
   attention` (open, asked before today Malaysia time) split by day, oldest day first (`Tue 22
   Sep`, ..., `Yesterday`), then `Today`. The sort within a day is remembered per user / contact.
3. **Clear one**: tap `Done`; the row moves to `Done today` with who and when; counts move.
4. **Repeat** to `Open 0`; the empty state says nothing is waiting.
5. **Look back**: `Show done` reveals the full done history (the #1333 list).
6. **The office** sees the same state, `done_by` and `done_at` on the customer's Asks tab.
7. **The sales admin** sees every agent's list with an Agent filter and per-agent counts; **a team
   leader** sees the same select limited to their team's current members. [Q7 (c)]

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
- **AC-ST105b [BE]** (#1366) An ask with `customer_id` NULL whose contact is linked (through
  `respond_contact_customers`) to two customers, one handled by A and one by B, appears in BOTH
  A's and B's `open` with `customer_name` null; an ask with no customer and an unlinked contact
  appears in nobody's; the portal and CRM PATCH scopes follow the same rule.
- **AC-ST106 [BE]** `open` holds every branch: an open `incoming` ask and a `console` ask are in
  `open` and count (Q5 (a)). [Q5]
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
- **AC-ST113 [FE][T]** `bucketTodo(payload, sort)` with `today_start = 2026-09-28T16:00Z` and
  the default sort `{id: 'asked_at', desc: false}`: sections are `Needs attention` then `Today`;
  an open ask at `2026-09-28T15:59Z` and one at `2026-09-27T20:00Z` sit in `Needs attention`
  under the day `Yesterday`; one at `2026-09-22T05:00Z` under `Tue 22 Sep`, and that day comes
  BEFORE `Yesterday` (oldest day first); one at `2026-09-28T16:00Z` sits in `Today`; a day with no
  open row is absent; counts read `{open: 4, needs_attention: 3, done_today: <len done_today>}`.
  Inside a day the rows follow `sort`: `asked_at` asc puts 15:59 after 20:00 of the previous
  day's group only within its own day; `{id: 'customer', desc: false}` orders a day's rows by
  customer name A to Z; `{id: 'branch'}` by branch label; `desc: true` reverses. [Q3][Q4]
- **AC-ST120 [FE]** CRM: the Sort select's value is read from and written to the listing view
  preference under key `sales.customer_asks.view::todo` through `useListingViewPreferences`
  (`sorting: [{id, desc}]`); a stored `{id: 'customer', desc: false}` is applied on open before the
  rows render; changing the select writes it (debounced, one PUT). [Q3]
- **AC-ST121 [FE]** Portal: the Sort select's value is remembered per contact in `localStorage`
  under `sorento.portalAsksSort.<contact_id>` (the landing default-tab pattern); a stored value is
  applied on open; a value for another contact is ignored. [Q3]
- **AC-ST114 [FE]** `AskTodoList` renders the counts line and the Sort select, the section
  headings in order (`Needs attention`, `Today`) with their day sub-headings (`Yesterday`, `Tue
  22 Sep`, ...), one row per ask with customer, contact, `CODE x Q`, branch badge (an `incoming`
  row shows `Incoming`), answer line, time asked, and a `Done` button; `Needs attention` rows
  carry an age label ("2 days ago") and the count in the header is `text-destructive` when > 0.
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
- **AC-ST119 [UX]** The done row leaves its group with the `motion.ts` fade preset
  (`surfaceExitTransition`, `visualDuration` 0.2 s: the visible fade settles in 150 to 200 ms,
  the spring tail reaches opacity 0 at about 280 ms, measured 29 Sep 2026 on both mounts) and
  renders instantly under `prefers-reduced-motion` (`duration 0.01`; the sandbox could not flip
  the media query, so that path is verified by the preset, not in a browser); nothing else on the
  page animates (`document.getAnimations()` empty; the Sonner toast region is the app's toast,
  not the page); `Done` carries the pressed-state token (`active:scale-[0.97]`).

## S2: the CRM mount, mine and every agent

- **AC-ST201 [BE]** `user_permissions` holds `sales.customer_asks.{view,add,edit,delete}` and
  `sales.customer_asks.view_all`; every role holding `sales.opportunities.view` holds `.view` and
  `.edit` and NOT `.view_all` (Q7 (c): a salesperson sees their own list, a leader their team;
  security review B1, 29 Sep); `admin` and `superadmin` hold all five; an `integration_*` role
  holds none. [Q7]
- **AC-ST202 [BE][T]** `agent_for_user(db, user)`: a user whose `respond_contact_id` is CA
  resolves agent A; a user with no contact, or a contact linked to no agent, resolves None.
- **AC-ST203 [BE]** `GET /api/v1/sales/customer-asks/todo` as the A-linked user returns AC-ST105's
  payload plus `agent: {code, name}`; as an unlinked user returns empty arrays and `agent: null`
  (200, not 403); without `sales.customer_asks.view` 403.
- **AC-ST204 [BE]** `GET .../todo?agent_id=<B>` with `view_all` returns B's payload; as a plain
  linked user (no `view_all`, leads no team) 403 `NOT_YOUR_AGENT`; an unknown agent id 404;
  `agent_id=all` with `view_all` returns every agent's open rows each carrying `agent_code`. [Q7]
- **AC-ST205 [BE]** `GET /api/v1/sales/customer-asks/agents` with `view_all` lists every agent
  that has at least one open ask with `{agent_id, code, name, open, needs_attention}` computed
  with the same rules as the payload; a plain linked user gets `[]` (200). [Q7]
- **AC-ST215 [BE]** Team leader (Q7 (c)): agent A leads active team T whose current members are A
  and B (`valid_to IS NULL`); C's membership of T ended (`valid_to` in the past); D is in no team.
  As the A-linked user without `view_all`: `/agents` lists A and B (with counts, 0 allowed) and
  not C or D; `todo?agent_id=<B>` returns B's payload; `agent_id=<C>` and `agent_id=<D>` are 403
  `NOT_YOUR_AGENT`; `agent_id=all` returns A's and B's rows with `agent_code`. A leader of an
  inactive team (`is_active = false`) is not a leader for this. [Q7]
- **AC-ST216 [BE]** The clear scope equals the view scope (Q7 (c)): as the A-linked leader without
  `view_all`, `PATCH .../customer-asks/{id}` `{state: done}` on B's ask is 200 with
  `done_by_user_id` = the leader's user and `done_by` = the leader's name; on C's and D's asks 404.
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
- **AC-ST210 [FE]** When `/agents` answers a non-empty list (view_all, or a team leader), an
  `Agent` `SearchableSelect` (clearable, `All agents` first) sits in the header actions listing
  those agents with their counts ("SEAN I · 4 open · 2 need attention"); picking one refetches
  with `agent_id`; clearing returns to mine; `All agents` shows every listed agent's rows with the
  agent code on line 1 (`showAgent`). With an empty list no select renders. [Q7]
- **AC-ST211 [FE]** `services/stockAskService.ts` exposes `getCustomerAsksTodo`, `listAskAgents`,
  `updateSalesAsk`, all via `apiFetch` + `extractApiError`; no component calls fetch.
- **AC-ST212 [E2E]** Sidebar from `/`: Sales > Customer asks as the A-linked user: the same
  counts and groups as AC-ST118, `Done` on one row moves it, reload persists; as admin the Agent
  select lists A and B with counts, picking B shows Z's asks. 375px and 1280px: no clipping.
- **AC-ST213 [BE][T]** `test_schema_uuid_id_principle.py` passes with no exemption; no response
  carries a bare `sales_agent_id` or `customer_id` beyond the ask's own `id` and `agent_id` in the
  agents list (the filter key, never shown).
- **AC-ST214 [E2E][FE]** The office marks an ask done on customer X's Asks tab: the portal to-do
  (CA) and the CRM to-do show it under `Done today` with the office user's name. [FE] The office
  Asks tab and the portal `Show done` history carry a `Done by` column: "Done by <name>, <time>"
  for a done row, "Done" when no name, `-` when open (journey step 6; reviewer blocker, 29 Sep).
- **AC-ST217 [FE]** `Done` and `Reopen` are disabled for the ask whose PATCH is in flight
  (`pendingAskId`); the CRM unlinked state is a heading "Not linked to a sales agent" plus one
  hint line, no button (reviewer nits, 29 Sep).

## S3: the reshape to the approved mockup (plan 0c, 3.6)

Supersedes on screen: AC-ST114 (counts line, age label, Sort select in the counts line), AC-ST115
(inline note on the row), AC-ST116 (truncated notice stays), AC-ST117 (portal body), AC-ST120 /
121 (the sort is now the toolbar's Sort, persistence unchanged), AC-ST209 / 210 (CRM page shape,
Agent select unchanged), AC-ST217 (pending state stays on the card's button and the sheet foot).

- **AC-ST301 [FE][T]** `askToSummary(ask)` maps an ask to the landing summary shape: `title` =
  `SRT5674 x 50`, `customer_name`, `contact_name`, `created_at`, `status` = the ask's state,
  `answer` = `askAnswerText(ask)`, `branch`; `askAnswerText` strips the `CODE x Q:` prefix from
  `answer_summary` and upper-cases the first letter ("SRT5674 x 50: yes, we have stock, ..." ->
  "Yes, we have stock, ..."); an `answer_summary` without the prefix is returned as is.
- **AC-ST302 [FE][T]** `ASK_LANDING_FIELDS` = Customer (text), Answer (text), Created (date, key
  `created_at`; the word the Sort button prints, ruled 30 Sep), State (status); `applyLandingFilters` over adapted asks with `{customer_name: 'Hock Lee Trading'}`
  keeps only that customer's rows; `sortLandingItems` with `{key: 'created_at', dir: 'asc'}` puts
  the oldest first, `{key: 'customer_name', dir: 'asc'}` A to Z.
- **AC-ST303 [FE][T]** `bucketTodo(payload, sort)`: sections `Needs attention` (open before
  `today_start`, one day group, oldest first under the default sort) and `Today`; no per-day
  sub-groups; `done` unchanged.
- **AC-ST304 [FE]** Both mounts render `LandingToolbar` (Filter, Sort reading `Created` by
  default, the list / cards toggle) and no New button; changing Sort re-orders inside each
  section and is remembered (CRM: `useListingViewPreferences` `sorting[0]` under
  `sales.customer_asks.view::todo`; portal: `localStorage sorento.portalAsksSort.<contact_id>`).
- **AC-ST305 [FE]** Cards view: one `Needs attention` heading (red) then `Today` then
  `Done today`; a card shows exactly customer + contact, `Asked: CODE x Q`, `Answered: <sentence>`,
  the datetime, and `Done` in the top-right slot (`Reopen` on a done card); no counts line, no
  age label, no badge, no Open link, no note input. Clicking the card body calls `onOpen(ask)`;
  clicking `Done` calls `onDone(askId)` and does not call `onOpen`.
- **AC-ST306 [FE]** List view: a `DataGrid` (`tableLayout` fixed, resizable, `listingKey`
  `sales.customer_asks.view::todo` on the CRM and `null` on the portal) with columns Asked at,
  Customer, Contact, Asked, Answered, (CRM: Agent when `showAgent`, Done by) and the action
  column LAST holding `Done` / `Reopen`; the groups are section rows in order Needs attention,
  Today, Done today; row click calls `onOpen`, the button does not.
- **AC-ST307 [FE]** The opened card (portal `Drawer`, CRM `Sheet`) renders: customer, contact,
  asked at (CRM: agent code); the Asked / Answered block with a `Jump to message` button; the
  conversation from `getAskConversation` with inbound bubbles left and outbound right, the
  `ask_message_id` bubble tagged `This ask`; `Show the whole day` refetches with `whole_day=true`;
  CRM only `Open in Conversations` link to that contact's chat history (the conversation payload
  carries `contact_id`, the `respond_contacts.id`, for this link only); a Note textarea whose `Save note` button calls
  `onNote(askId, text)` (blur does not) and then shows `Saved <time>`; foot `Done` calling
  `onDone` (or `Reopen`). Clicking `Jump to message` scrolls the tagged bubble into view (the
  bubble element receives the flash class).
- **AC-ST308 [FE]** Empty payload: "Nothing waiting" heading + hint, no button; the toolbar still
  renders. Loading: skeleton. Error: the error block.
- **AC-ST309 [BE]** `GET /api/v1/public/portal/customer-asks/{id}/conversation` as CA for an ask
  of X (contact CX): messages of `chat_histories` for CX with `sent_at` within 30 minutes of the
  ask's `created_at`, oldest first, each `{id, direction in|out, text, at}` and nothing else (no
  `message_id`, `result`, `respond_ts`, `delivery_status`); rows outside the window absent;
  another contact's rows absent; at most 60 rows. `ask_message_id` is the id of the outgoing row
  after `created_at` whose text contains the ask's `answer_summary`; with no such row, the nearest
  outgoing row after `created_at`; with none, null. An ask of Z (another agent) is 404; a contact
  with the switch off 403; an ask with no contact answers `messages: []`.
- **AC-ST310 [BE]** `?whole_day=true` returns the rows of the ask's Malaysia calendar day (a row at
  `today_start - 1s` of that day absent, a row 5 hours before the ask present), at most 200.
- **AC-ST311 [BE]** `GET /api/v1/sales/customer-asks/{id}/conversation` under
  `sales.customer_asks.view` follows the PATCH scope: mine 200, a team member's 200 for the
  leader, Z's 404 without `view_all`, 200 with it; same payload rules as AC-ST309.
- **AC-ST312 [E2E]** Portal as CA at 375: Customer asks tab shows the toolbar and the three
  sections; tap a card: the sheet shows the conversation with the tagged bubble; `Jump to
  message` scrolls to it; type a note, `Save note`, "Saved" appears; `Done` at the foot closes
  the sheet and the card moves to Done today; switch to list view: the grid with Done rightmost,
  scroll sideways reaches it. CRM at 1280: sidebar to Customer asks, pick SEAN I, same in cards
  and list; the right sheet opens on row click; `Open in Conversations` leads to that contact's
  chat history.
