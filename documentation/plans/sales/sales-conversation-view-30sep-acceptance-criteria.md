# UAC: Conversation view for sales agents in the sales portal (lane SALES-CONVO)

Status: draft under the plan's recommendations (Q1 read-only, Q2 latest first, Q3 cards + list);
each criterion marked `[Q<n>]` changes if the owner rules otherwise. Plan:
`PLAN-sales-conversation-view-30sep.md`. Mock: `mockups/sales-conversation-30sep-mockup.html`.

## A. Who sees the kind

- AC-CV1: a portal contact linked to a sales agent, with the `conversation` portal form switched
  on for them, sees "Conversation" in the landing's kind picker with a count badge (the number of
  rows in A/AC-CV4), in the picker's usual order after Customer asks.
- AC-CV2: a contact with the switch off does not see the kind; the list route answers 403
  `FORM_TYPE_NOT_VISIBLE`.
- AC-CV3: a contact linked to no sales agent does not see the kind; the list route answers 403
  `NOT_A_SALES_AGENT`. A `?type=conversation` deep link for either falls back to the first visible
  kind, like every other kind.

## B. The list

- AC-CV4: one row per WhatsApp contact linked (`respond_contact_customers`) to a customer whose
  `sales_agent_id` is the caller's agent and that has at least one `chat_histories` row. A
  customer with no linked contact, or a contact with no chat, is not a row. Another agent's
  customer is never a row, and its thread route answers 404.
- AC-CV5: each row shows the customer name, the contact name, the phone, the last message text
  (WhatsApp markup stripped, one line, truncated) with an in/out arrow, and when it was sent
  (relative for today, the date otherwise; full Malaysia date-time on hover).
- AC-CV6: a row whose last message is incoming is tinted and labelled "Customer wrote last"; an
  outgoing last message is a plain card.
- AC-CV7 `[Q2]`: default order is last message newest first. The Sort button offers Last message
  and Customer; the choice is remembered per contact (same mechanism as Customer asks) and
  survives a reload.
- AC-CV8 `[Q3]`: the landing's Cards / List toggle applies; List is the landing DataGrid with the
  columns Customer, Contact, Last message, When, header click sorts the same state, and a row
  opens the same Drawer as a card. Cards is the default at every width.
- AC-CV9: the landing search box narrows the rows by customer name, contact name, phone or last
  message text, server-side, debounced like the other kinds. Filter offers Customer, Contact and
  a Last message date range.
- AC-CV10: no New button. Empty state "No conversations yet" with the hint; a search or filter
  with no match shows "No conversation matches ..." with Clear filters.
- AC-CV11: usable and unclipped at 375px and 1280px.

## C. The thread

- AC-CV12: tapping a card opens the bottom Drawer (`max-h-[90dvh]`) with `RespondChatList`: the
  WhatsApp header (avatar initial, customer and contact name, phone), date pills, incoming and
  outgoing bubbles with the sender label and receipt ticks the ticket drawer shows, and the
  contact's internal notes in amber.
- AC-CV13: scrolling up loads older pages until "Beginning of this conversation"; the
  jump-to-latest button appears when scrolled up and shows the count of newer messages.
- AC-CV14: the header search finds messages in the whole thread (server search), steps between
  matches and jumps to a match outside the loaded window, exactly as in the ticket drawer.
- AC-CV15 `[Q1]`: no composer, no reply, no note writing; nothing in the Drawer sends anything.
- AC-CV16: the thread and search routes are portal-token routes that apply the same agent scope
  as the list (AC-CV4); a contact id outside the scope is 404, never a thread.

## D. Admin

- AC-CV17: the kind appears in the Contact page's Portal forms switches and in the market
  segment "Additional portal forms" list with the label "Conversation", through the shared kind
  list, without a separate admin change.

## E. Tests (Phase 2, written before the code)

- pytest: AC-CV2, AC-CV3, AC-CV4 (own vs other agent, no contact, no chat), AC-CV7 order,
  AC-CV9 search, AC-CV16 scope on page and search.
- vitest: the list renders rows and the tint (AC-CV5, AC-CV6), the empty states (AC-CV10), the
  picker shows the kind only when granted (AC-CV1), the Drawer mounts `RespondChatList` with no
  composer (AC-CV12, AC-CV15).
- Browser evidence: agent-browser run of the landing at 375 and 1280 (AC-CV11), a card open, a
  search in the thread.
