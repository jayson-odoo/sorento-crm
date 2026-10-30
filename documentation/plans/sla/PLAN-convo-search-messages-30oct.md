# PLAN: Conversations inbox search finds message text (CONVO-SEARCH-MESSAGES)

Status: in review (small fix track: no migration, no auth/RBAC change, no new ingest surface; the
production diff is ~230 changed lines, the rest is tests, this plan, its UAC and the hand-test
script). UAC: `convo-search-messages-30oct-acceptance-criteria.md`.

## Journey

Owner, 30 Oct 2026, on Dashboards > SLA > Conversations: "i think from here need to be able to
search by messages". The one search box ("Search name or phone") must also find a conversation by
the text of any stored message, inbound or outbound.

## What exists (measured)

- Page: `sorento_crm_frontend/app/(protected)/sla-management/conversations/` -
  `components/ConversationListPane.tsx` (search box, rows), `hooks/useConversationsInbox.ts`,
  `services/conversationsInboxService.ts` (`GET /api/v1/sla-management/conversations?tab=&q=`).
- API: `sorento_crm_backend/app/api/v1/sla/conversations.py` `list_inbox_conversations`, scoped by
  `_own_contact_ids` (view_own holders) - the access rule the search must keep.
- Service: `sorento_crm_backend/app/services/conversation_inbox_service.py` `list_conversations`:
  one keyset SQL statement; `q` today is `name ILIKE` OR `phone_number ILIKE` only.
- In-thread search: `conversation_thread_service.search_thread` (ILIKE over `chat_histories.message`,
  OTP-masked snippet, rows without `message_id` skipped). The chat MCP / analytics
  `search_messages` is a generic dataset query with offset paging; not a fit for a keyset inbox.
- Index: `ix_chat_histories_message_trgm` (alembic 327, pg_trgm GIN on `message`) already serves
  `ILIKE '%q%'`. No new index or migration.

## Behaviour

- One box, placeholder "Search name, phone or message".
- A contact whose name or phone matches shows as today (last message snippet).
- Otherwise a contact with a matching message (newest match) shows that message's snippet with the
  term highlighted, direction arrow of that message, its time; message-only matches are ordered
  newest match first (Mentioned keeps its own mention clock).
- Click opens the thread centred on the matched message (`around=` page) with the term highlighted.
- Tabs and `view_own` scoping apply unchanged (same statement, same conditions).
- Plain case-insensitive substring: works for Malay / Chinese / English alike.
- OTP texts: a term with no digit cannot hit a masked code; a term WITH a digit skips OTP-shaped
  messages. (An always-on `regexp_replace` re-check was tried first and measured 7.6 s on a phrase
  at 400k messages: no statistics, a 1-row estimate, a nested loop. See the CTE docstring.)
- Matches are WhatsApp-channel only, the channel the thread reads, so every match opens.

## Tests (red first)

- pytest: message-text match (in / out), name match keeps last snippet, newest-match ordering,
  tab respected, view_own scope respected, OTP code is not searchable, keyset cursor over matches.
- vitest: row renders match snippet with `<mark>`, click passes the matched message id, thread
  jumps to it.
