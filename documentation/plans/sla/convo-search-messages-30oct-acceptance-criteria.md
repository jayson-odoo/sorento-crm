# UAC: Conversations inbox search finds message text (CONVO-SEARCH-MESSAGES)

Plan: `PLAN-convo-search-messages-30oct.md`. Tests:
`sorento_crm_backend/tests/test_conversations_inbox_message_search.py` (BE) and the
`ConversationListPane` / `ConversationThreadPane` / `ConversationsInbox` vitest suites (FE).

- **AC-S1** The one search box (placeholder "Search name, phone or message") finds a contact by the
  text of any stored WhatsApp message, sent or received, as a case-insensitive substring. Works the
  same for English, Malay and Chinese; `%` and `_` are literal.
- **AC-S2** A contact whose name or phone matches reads exactly as before: latest message, no
  highlight (`match` is null), even when one of its messages also contains the term.
- **AC-S3** Otherwise the row shows the contact's NEWEST matching message instead of the latest
  message: snippet with the term highlighted and kept near the front of the line, that message's
  time and direction arrow.
- **AC-S4** Message-only matches sort newest match first; name hits keep their latest-message
  time on the same keyset, and paging over a search has no gaps and no duplicates, one SQL
  statement per page. Mentioned keeps its mention order.
- **AC-S5** The active tab (Mine / Mentioned / Unassigned / All) and the viewer's `view_own` scope
  still decide who is listed.
- **AC-S6** Clicking a row found by a message opens the thread centred on that message, ringed,
  with the term highlighted. A name match opens on the latest messages as before.
- **AC-S7** A sign-in code is never findable by its digits, and a snippet never shows one.
- **AC-S8** A message the thread cannot open (no message id, or a non-WhatsApp channel) is not a
  match.
- **AC-S9** Fast at scale: no new index (alembic 327's trigram index serves it); measured 120 to
  600 ms per page at 20k contacts / 400k messages for words, phrases, digits and CJK.
