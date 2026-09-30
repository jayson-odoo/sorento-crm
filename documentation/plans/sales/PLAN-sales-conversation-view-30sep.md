# PLAN: Conversation view for sales agents in the sales portal (lane SALES-CONVO)

Status: built 30 Sep 2026 to the approved mock (owner rulings Q1 read only, Q2 latest first, Q3 both,
30 Sep); pytest 19 new + 146 neighbouring green, vitest 14 new green, browser-verified with
agent-browser at 375 and 1280 (evidence in `evidence/sales-conversation-30sep/`); hand test filed
(`laneboard/scripts/1384.md`); awaiting review, hand test, CI and merge. Track: full (no migration,
one new portal router, one new grantable kind; security review needed: new portal-token surface).
Plan created: 2026-09-30
Domain: sales (the salesperson's own surface, beside `PLAN-sales-asks-todo-29sep.md`).
Branch: `claude/sales-conversation-view-0wzzl1` (stands in for `crew/sales-convo`), PR #1384.
Sibling: lane ASKS-UX makes the Customer asks detail sheet use the same conversation component;
no PR from it is open as of 30 Sep 00:50 UTC. Coordinate through crew if both touch
`components/stock-asks/AskConversationPanel.tsx` or the Customer asks Drawer mount.

## 0. Owner words (30 Sep 2026, binding)

> "Customer asks is good, but what if I want to see the conversation."

In the sales portal ("Welcome, <name>", the view dropdown that lists Price Tag Request and
Customer asks), add a view "Conversation": as a sales agent I see the WhatsApp conversations of
the customers assigned to me.

## 1. Mock

`documentation/plans/sales/mockups/sales-conversation-30sep-mockup.html`, one self-contained
static HTML file. Frames: A cards landing at 375px, B list (DataGrid) landing at 768px, C the
opened thread (read-only, recommended), D the option (b) reply composer, E empty states. The
three open questions and their recommendations are at the bottom of the mock and in section 3.

## 2. Findings (read from the code, 30 Sep 2026)

### 2.1 Where the view goes

- The landing is `sorento_crm_frontend/app/(auth)/portal/components/PortalLanding.tsx`. The
  kind picker is the `SearchableSelect` at lines 594-637 over `landingKindsFor(contact)`
  (lines 112-120), which is `LANDING_KINDS` filtered by the server's `visible_form_types`.
- `customer_asks` is the precedent for a kind with no form: `PortalLanding.tsx:668-674` renders
  `CustomerAsksList` as the body, and its `loadAll` leg (lines 384-388) only reads a count for
  the picker badge. The new kind follows the same two branches.
- Kinds and labels: `sorento_crm_frontend/lib/portal-form-kinds.ts` (`CUSTOMER_ASKS_KIND` at
  line 65, `LANDING_KINDS` at 74-79, `LANDING_LABELS` at 106-111). `EMPTY_LISTS` and `totals`
  in `PortalLanding.tsx:122-130` and `462-470` enumerate every kind by hand and gain a row.
- Server side the kind is switched per contact like Customer asks: `GRANTABLE_PORTAL_FORM_TYPES`
  in `sorento_crm_backend/app/services/portal_service.py:89-94`, resolved by
  `switched_form_types` in `app/services/portal_form_visibility_service.py:76-96` (base kinds,
  segment grants, then `contact_portal_form_overrides`). Off by default, so the owner turns it
  on per salesman from the Contact page's Portal forms section.

### 2.2 How "customers assigned to me" resolves

- Portal token -> contact -> sales agent: `sales_agent_for_contact` in
  `app/services/price_tag_request_service.py:109-128`, delegating to `agent_for_contact` in
  `app/services/sales/portal_agent.py:19-44` (`sales_agents.contact_id`, ordered so a double link
  answers the same agent every time). The Customer asks route gates on it in
  `app/api/v1/public/portal_customer_asks.py:37-51` (403 `NOT_A_SALES_AGENT`, then 403
  `FORM_TYPE_NOT_VISIBLE`); the new route reuses `_agent_id` unchanged apart from the form type.
- Agent -> customers: `customers.sales_agent_id` (`app/models/order.py:146-150`), read through
  the one seam `_owning_agent_column` / `_agent_scope` in `app/services/stock_ask_service.py:
  653-708` (crew ruling 29 Sep: swap to CONTACT-CUSTOMERS' relation, PR #1366, in one place).
- Customer -> WhatsApp contact: `respond_contact_customers` (`app/models/access.py:11-64`,
  contact_id -> `respond_contacts.id`, customer_id -> `customers.id`, company-scoped).
- Contact -> thread: `respond_contacts.respond_io_id` (`app/models/access.py:238`) is the
  `chat_histories.contact_id` key (`app/models/chat_history.py:27`); the latest message per
  contact is the `DISTINCT ON (contact_id)` the CRM inbox already runs
  (`app/services/conversation_inbox_service.py`, module docstring and line 136, served by
  `ix_chat_histories_contact_sent_desc`).

So the list is: agent's customers, joined to their linked contacts, joined to each contact's
latest chat row; a customer with no linked contact or no chat is not a row.

### 2.3 The thread component to reuse

- `components/common/RespondChatList.tsx` is THE thread: WhatsApp header with avatar, name,
  phone and search (lines 828-852), date pills, incoming white and outgoing green bubbles with
  sender label and receipt ticks (984-1105), internal notes in amber (891-934), the scroll-back
  and newer-page loaders, and the jump-to-latest button with the unseen count (1130-1156).
- `TicketConversationPanel.tsx` (`app/(protected)/sla-management/conversation-sla-tracking/
  components/`) shows the wiring: `useConversationThread` over `liveItems`, `loadPage` and
  `searchMessages` (lines 169-179), then `RespondChatList` with the thread's props (243-289).
  The portal mount needs the same three loaders behind portal-token endpoints, and no comments,
  media proxy or composer for the read-only cut.
- The portal already mounts a chat in a bottom `Drawer` for Customer asks
  (`app/(auth)/portal/components/CustomerAsksList.tsx:122-150`, `max-h-[90dvh]`); the
  Conversation kind uses the same Drawer with `RespondChatList` inside instead of
  `AskConversationPanel` (which draws its own simplified bubbles, lines 139-169, and is the
  file lane ASKS-UX is changing).

### 2.4 Existing contact-keyed thread endpoints (CRM, staff permission)

`app/api/v1/sla/conversations.py`: `GET /{contact_ref}/page` (line 83, before/after/around
paging), `GET /{contact_ref}/search` (120), `GET /{contact_ref}/comments` (143), all gated by
`sla_management.conversations.view`. The portal cannot call these (portal token, not a staff
session), so the build adds portal twins under `/api/v1/public/portal/conversations/...` that
call the same service cores (`ConversationSLATrackingService.fetch_contact_thread_page`, the
search core) after the agent scope check, exactly the way the ticket-keyed and contact-keyed
twins already share one core.

## 3. Open questions for the owner (settled on the mock)

1. Read-only vs reply. Recommendation (a) read-only: a portal reply goes out on the business
   number as the CRM, needs the 24-hour template rule and an audit identity for a portal
   token holder; the composer exists (`SharedConversationComposer`) and can be a second slice.
2. Sorting. Recommendation (a) latest message first, Sort menu offers Customer A to Z,
   remembered per contact like Customer asks (`usePortalAsksSort`).
3. Card vs list. Recommendation (a) both through the landing's existing toggle, cards default,
   list as the landing DataGrid (Customer, Contact, Last message, When).

## 4. Build (30 Sep 2026, as shipped)

- BE: `app/api/v1/public/portal_conversations.py`: `GET /conversations` (agent scope, latest
  message per contact, `q`, keyset or page), `GET /conversations/{contact_id}/page`,
  `GET /conversations/{contact_id}/search`; `CONVERSATION_FORM_TYPE = "conversation"` in
  `portal_service.py` beside `CUSTOMER_ASKS_FORM_TYPE`. Tests first (tester agent): scope
  (another agent's customer is 404), the two 403s, the switch, paging.
- FE: `CONVERSATION_KIND` in `portal-form-kinds.ts`; `ConversationList.tsx` under
  `app/(auth)/portal/components/` (toolbar, cards, DataGrid list, Drawer with
  `RespondChatList` + `useConversationThread`); `lib/portal-conversations-service.ts`; the two
  `PortalLanding.tsx` branches. Vitest on the list and the empty states.
- Admin: the kind appears in the Contact page's Portal forms switches and the market segment
  "Additional portal forms" automatically through `ADDITIONAL_LANDING_KINDS`.

## 5. Build notes

- Rulings applied: read-only thread (no composer, no `onReply`, Copy stays), latest message first
  with Sort offering Customer, cards default with the landing's toggle and the DataGrid list.
- Files: BE `app/api/v1/public/portal_conversations.py`, `app/services/portal_conversation_service.py`,
  `app/schemas/portal_conversation.py`, kind + agent-only gate in `portal_service.py` /
  `portal_form_visibility_service.py`, router mount in `public/__init__.py`; FE
  `lib/portal-form-kinds.ts` (`CONVERSATION_KIND`), `app/(auth)/portal/lib/conversations-service.ts`,
  `conversation-landing.ts`, `hooks/usePortalConversations.ts`, `components/ConversationList.tsx`,
  `components/ConversationThread.tsx`, the two `PortalLanding.tsx` branches.
- The list carries `contact_id` (`respond_contacts.id`) as the only key; the thread routes accept
  that id only (a phone number or a Respond id is 404), and every thread read re-runs the list's
  own scope query for that one contact, so "may open" and "is a row" cannot disagree.
- Internal notes are NOT served to the portal (security review 30 Sep, findings 1 and 2: a
  portal token is not a staff session, and `conversation_ticket_comments` is not company-scoped,
  so a shared contact's notes from another company would reach the agent). The approved mock's
  drawer frame shows one note; the shipped thread is messages only. Bringing notes back needs an
  owner ruling plus a company-scoped, portal-shaped comment read (crew-ask filed on PR #1384).
- Follow-up (security review finding 4, not blocking): the thread page read reaches Respond.io
  and fills the local cache on every call; a per-token rate limit on the two thread routes is a
  ticket, the exposure is bounded to the caller's own scoped contacts.
- Process note: the red tests were written first (backend commit 1c9d... `test(portal)`, then the
  FE specs) and made green in the same session rather than by separate tester / coder agents; the
  reviewer and security-reviewer passes ran as agents (Phase 3).
- Not touched: `AskConversationPanel.tsx`, `RespondChatList.tsx`, `conversation_thread_service.py`,
  `portal_customer_asks.py` (lane ASKS-UX, PR #1385, reshapes those); the two-step agent gate is a
  local copy in the new router for that reason.
