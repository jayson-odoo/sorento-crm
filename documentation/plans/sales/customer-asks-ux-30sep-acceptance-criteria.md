# UAC: Customer asks view fixes (lane ASKS-UX)

Plan: `PLAN-customer-asks-ux-30sep.md`. Numbering AC-AU<nn>. Tags: [BE] pytest (Postgres),
[FE] vitest, [E2E] hand test, [T] pins a rule.

## Item 1: filter by contact

- **AC-AU01 [FE][T]** `ASK_LANDING_FIELDS` carries a `contact_name` field labelled `Contact`
  after `Customer`; `filterTodoPayload(payload, { contact_name: 'Jayson' })` keeps only the asks
  whose `contact_name` is exactly `Jayson`, in `open` and `done_today` alike.
- **AC-AU02 [FE]** On the portal Customer asks tab the Filter popover shows a `Contact` select
  whose options are the distinct contact names of the loaded asks; picking one narrows the cards.
  Same on Sales > Customer asks (both mounts pass the same table).

## Item 2: Show done follows the view

- **AC-AU03 [FE]** With Cards chosen, `Show done` renders the done history as `AskCard`s (no
  column header in the document) under a `Done` heading, paged; with List chosen it renders the
  DataGrid as before. Switching the view while the history is open switches it too.
- **AC-AU04 [FE]** A done card's `Reopen` goes through `updateCustomerAsk(id, { state: 'open' })`
  and the to-do refetches; the card itself opens the conversation Drawer.
- **AC-AU05 [FE]** An empty done history in Cards view reads `No done asks yet`.

## Item 3: the full conversation

- **AC-AU06 [BE]** `GET /api/v1/public/portal/customer-asks/{id}/conversation/page` with no
  cursor answers the newest window of the ask's contact thread, oldest first, in the shape of
  `GET .../conversation-sla-tracking/{id}/conversation/page` (`items`, `has_more_older`,
  `has_more_newer`, `oldest_message_id`, `newest_message_id`, `anchor_message_id`, `source`,
  `error`, `backfilled`); `before=<message_id>` answers older rows; `around=<message_id>` centres
  on it with `anchor_message_id` set. Two cursors at once is 422. Same for
  `GET /api/v1/sales/customer-asks/{id}/conversation/page`.
- **AC-AU07 [BE]** `GET .../conversation/search?q=` answers the newest-first matches of the ask's
  contact thread (`items[].message_id`, `sent_at`, `direction`, `snippet`, plus `total`,
  `truncated`, `query`); rows of another contact and rows with no `message_id` never match.
- **AC-AU08 [BE]** Scope and gate are those of `GET .../conversation`: another agent's ask is 404,
  an unknown id 404, a contact who is no agent 403 `NOT_A_SALES_AGENT` (portal), an ask with no
  contact or a contact with no Respond id answers the empty page / empty search (200).
- **AC-AU09 [BE]** `GET .../conversation` also carries `ask_message_ref`: the Respond `message_id`
  (string) of the row `ask_message_id` names, `null` when that row has no `message_id` or there is
  no such row.
- **AC-AU10 [FE]** The opened ask (portal Drawer and CRM Sheet) shows the shared thread
  (`RespondChatList`): the loaded tail with older pages on scroll-back, the search affordance, the
  jump-to-latest control, and the anchor bubble tagged `This enquiry`; no `Show the whole day`.
- **AC-AU11 [FE]** On open, the thread jumps to the anchor (scroll when it is loaded, the page
  around it when it is not); `Jump to message` repeats the jump. Without an anchor the button is
  disabled and nothing is tagged.
- **AC-AU12 [FE]** The mount reads the tail through the page loader (no cursor) and the anchor
  through `getAskConversation`; both live in the mount's service file (portal `portalFetch`, CRM
  `apiFetch`), never in the panel.
- **AC-AU13 [E2E]** Hand test: an ask asked before today opens with its whole history reachable,
  the asked message highlighted and `Jump to message` landing on it.
