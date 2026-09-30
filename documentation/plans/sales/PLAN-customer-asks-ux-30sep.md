# PLAN: Customer asks view fixes (lane ASKS-UX)

Status: items 1 to 4 built and green 30 Sep 2026 (item 4 = option a, owner ruling) (pytest 45 on the three ask suites, vitest on the touched suites), PR #1385, hand test PASSED, awaiting CI and merge. Track: small fix (no migration, no auth or RBAC change, no new
external ingest surface; two new read routes per mount under the EXISTING ask gate, one new key on
an existing response). Items 1 to 3 build now; item 4 is a scout (section 5), owner decides.
Plan created: 2026-09-30
Domain: sales. Builds on `PLAN-sales-asks-todo-29sep.md` (the to-do, the conversation panel)
and its UAC (`sales-asks-todo-29sep-acceptance-criteria.md`).
UAC: `customer-asks-ux-30sep-acceptance-criteria.md` (same folder).

## 0. Owner feedback (30 Sep 2026, prod, portal "Customer asks" under "Welcome, <name>")

1. Filter must be able to filter by the asker (the contact, e.g. "Jayson").
2. Show done / Hide done: in Card view the done asks must render as cards; in List view as a list.
   Today, with Card view chosen, the done section is a table ("No data available").
3. The ask detail's Conversation shows only today's messages. Show the full history with the
   existing conversation component (WhatsApp bubbles, "This enquiry" highlight, search, jump to
   bottom), scrolled to the asked message; "Jump to message" must work. Reuse, do not re-implement.
4. Card title shows the contact ("Jayson"); the owner wants the customer ("Hanlim") and asks
   whether a customer group is needed since the contact links to six Hanlim customer records.
   Scout only (section 5).

## 1. Where each defect is (file:line, read 30 Sep)

**Item 1.** `LandingToolbar` builds its Filter popover from the field table it is given
(`app/(auth)/portal/components/LandingToolbar.tsx:76-96`). The asks kind's table is
`ASK_LANDING_FIELDS` in `lib/stock-asks-todo.ts:123-130`: Customer, Product, Answer, Created,
State. No contact field, although `askToSummary` (`lib/stock-asks-todo.ts:102-117`) already
carries `contact_name` on every row. `filterTodoPayload` (`:156-173`) applies the same table, so
adding the field is the whole fix, on both mounts (the CRM page passes the same table,
`app/(protected)/sales/customer-asks/components/MyCustomerAsksClient.tsx:125`).

**Item 2.** `CustomerAsksList.tsx:117-120` renders `CustomerAsksHistory` under the `Show done`
button whatever `view` is, and `CustomerAsksHistory.tsx:197-217` is a DataGrid only. The to-do
above it (`AskTodoList`) already switches on `view` (`components/stock-asks/AskTodoList.tsx:104`).
"No data available" is the grid's own empty state; the owner had no done ask on the shown page.

**Item 3.** Root cause: `stock_ask_service.conversation_for_ask`
(`sorento_crm_backend/app/services/stock_ask_service.py:884-925`) returns the `chat_histories`
rows within 30 minutes either side of the ask (cap 60, `CONVERSATION_MINUTES = 30`,
`:868-870`) or, with `whole_day=true`, the ask's Malaysia day (cap 200, `:907-912`). That is the
plan 3.6 design ("the chat around the ask"), so an ask opened days later shows only the minutes
around it and "Show the whole day" only widens to that day. The panel then draws its own bubbles
(`components/stock-asks/AskConversationPanel.tsx:139-169`) instead of the shared thread.

The existing conversation component is `RespondChatList` (`components/common/RespondChatList.tsx`)
driven by `useConversationThread` (`components/common/conversation/useConversationThread.ts`),
mounted in the ticket drawer by `TicketConversationPanel`
(`app/(protected)/sla-management/conversation-sla-tracking/components/TicketConversationPanel.tsx:243-289`):
scroll-back (`onLoadOlder`), a detached window with "Jump to latest", in-thread search
(`searchController`), `highlightMessageId` + `highlightLabel="This enquiry"`, and a caller-driven
jump (`focusMessageId` / `focusNonce`, `thread.jumpToMessage`). The hook needs two loaders per
surface: `loadPage({before|after|around, limit})` and `searchMessages(q)`
(`useConversationThread.ts:51-73`). Their backend cores are contact-keyed and already shared by
the ticket-keyed and inbox routes: `conversation_thread_service.fetch_thread_page` (`:719-763`,
Respond live lane with the local `chat_histories` lane as fallback) and `search_thread`
(`:786-833`); `ConversationSLATrackingService._thread_page_for_contact` (`sla_service.py:5931-5964`)
shows the client wiring (`RespondClient.for_identifier`).

Thread items are keyed by the Respond message id (`_row_to_item`,
`conversation_thread_service.py:183-211`: `messageId = int(row.message_id)`), whereas
`ask_message_id` is the `chat_histories.id` (`stock_ask_service.py:939-946`). The thread can only
highlight or jump to a Respond message id, so the ask endpoint must also name that id.

## 2. Design (simplest that works)

### Item 1 (FE only)
Add `{ key: 'contact_name', label: 'Contact', type: 'text' }` to `ASK_LANDING_FIELDS` after
Customer. Filter and Sort share the table, so Sort gains Contact too; `normalizeAskSort` accepts
it. Label "Contact" matches the list column header (`AskTodoGrid`, `CustomerAsksHistory.tsx:101`).

### Item 2 (FE only)
`CustomerAsksHistory` takes `view`, `onOpen` and `onReopen`. In `board` view it renders the same
paged rows as `AskCard`s (the card the to-do uses, `components/stock-asks/AskCard.tsx`) inside the
same `DataGrid` provider so `DataGridPagination` keeps paging (the provider is a context,
`components/ui/data-grid.tsx:212-220`; the table markup is only `DataGridTable`). A card opens the
conversation Drawer through the to-do's `open`; Reopen goes through `todo.reopen` so the to-do
reloads and the history reloads with it (`refreshKey`). List view is unchanged. The empty page
reads "No done asks yet" in board view (the grid keeps its own empty state).

### Item 3 (BE + FE)
Backend, both mounts, same gate and scope as the existing `/conversation` route
(`get_ask_in_scope`; portal `_agent_id` 403s, CRM `_patch_scope`):
- `GET /api/v1/sales/customer-asks/{ask_id}/conversation/page?before|after|around&limit`
- `GET /api/v1/sales/customer-asks/{ask_id}/conversation/search?q&limit`
- `GET /api/v1/public/portal/customer-asks/{ask_id}/conversation/page` and `.../search`
Service: `stock_ask_service.conversation_page_for_ask(db, ask, ...)` and
`conversation_search_for_ask(db, ask, q, limit)` resolve the ask's `RespondContact` through
`thread_contact_for` and call the two cores above with the same per-contact `RespondClient`
wiring the SLA service uses (`RespondClient.for_identifier`). An ask with no contact, or a contact
with no Respond id, answers `empty_page` / `empty_search` (200, shape-identical), as the ticket
routes do. Response shapes are byte-identical to the ticket-keyed twins.
- `conversation_for_ask` adds `ask_message_ref: str | None`, the Respond `message_id` of the row
  `ask_message_id` names (None when that row has none). `messages` and `ask_message_id` stay as
  they are (nothing else reads them; removing them is a follow-up, not this lane).

Frontend: `AskConversationPanel` drops its own bubbles and "Show the whole day" and mounts
`RespondChatList` fed by `useConversationThread`, with the loaders and the live tail supplied by
the mount (portal: `customer-asks-service.ts` via `portalFetch`; CRM: `stockAskService.ts` via
`apiFetch`), memoised in a hook per mount (`useAskThreadLoaders`), the UI -> hook -> service rule.
The live tail is the page endpoint with no cursor, polled every 10 s while the panel is open (the
ticket drawer's fallback cadence, `TicketConversationPanel.tsx:37`). Once the anchor
(`ask_message_ref`) is known the panel calls `thread.jumpToMessage(anchor)` once, which scrolls to
the bubble when it is in the tail window and loads the page around it (a detached window with
"Jump to latest") when it is not; "Jump to message" calls the same. `highlightMessageId={anchor}`
with `highlightLabel="This enquiry"`, no composer, no comments, no reply, no media proxy (the
portal thread precedent, `RespondChatList.tsx:179-180`). `Open in Conversations` stays CRM only.

## 3. Tests (red first)

Backend (`tests/test_customer_asks_thread.py`, Postgres blank schema, `_ask_todo_seed`):
- page: no cursor = newest window oldest-first; `before` walks older; `around` centres; another
  agent's ask 404, stranger 403 (portal), no contact = empty page (200); at most one cursor 422.
- search: matches by ILIKE with `message_id`, newest first; other contact excluded.
- `ask_message_ref`: the answer row's `message_id` as a string, None when the row has none.
Frontend (vitest):
- `lib/stock-asks-todo.test.ts`: `ASK_LANDING_FIELDS` has Contact; `filterTodoPayload` narrows by
  `contact_name`.
- `CustomerAsksList.test.tsx`: Filter popover offers Contact and narrows to Jayson's asks; Show
  done in board view renders cards (no columnheader) and in list view the grid; a done card's
  Reopen goes through `updateCustomerAsk`.
- `AskConversationPanel.test.tsx`: renders `RespondChatList` (data-testid `respond-chat-list`),
  tags the anchor bubble "This enquiry", exposes search, "Jump to message" jumps to the anchor,
  no "Show the whole day".
- `MyCustomerAsksClient.test.tsx` / portal list: opening a card fetches the tail page and the
  anchor.

## 3b. Review rounds (30 Sep 2026)

Reviewer: no blockers; applied: a failed tail poll keeps the loaded thread, the done-history
pager also shows past page 1, `RespondChatList` honours reduced motion on every programmatic
scroll. Security reviewer (the two portal routes are a new external read surface, so it ran
after all): one blocker fixed, thread cursors were spliced unvalidated into the Respond URL path
(`conversation_thread_service.py` `_cursor`, `RespondClient.get_message` quotes the id); the
portal page read is projected through `portal_thread_item` (no staff identity, no transport
ids); search text capped at 200. Open for the owner (crew-ask on PR #1385): how much of the
contact's thread an ask may reveal, and to whom (as built, a window, or the inbox permission on
the CRM).

## 4. Out of scope

Sending from the ask panel; media proxy on the portal; removing `messages` from `/conversation`.

## 5. Item 4: customer shown on the card, and grouping the six Hanlim customers

Scouted and reported on PR #1385 (crew-ask, file:line evidence). Owner ruling 30 Sep 2026:
option (a), the derived trading-name label. Built in `stock_ask_service._family_names_by_contact`
(read by `serialize`): an ask written against no customer whose contact's links are all ledgers
of one shop (`ledger_family_key`, the chatbot's rule) is named by `ledger_family_label`
("HANLIM TRADING SDN BHD"); links to two shops keep the contact fallback; an ask written against
a customer is untouched. No schema, no UI. Tests: `tests/test_stock_ask_family_label.py`.
Hand test of items 1 to 3 PASSED on 10ec2f86 (owner: "#1385 UIX is okay"). The thread exposure
question (section 3b) stays as built pending the owner's answer.
