# PLAN: Conversation view for sales agents in the sales portal (SALES-CONVO)

Status: Plan (mock in progress; owner approval of the mock gates the build). Track: to be named once the mock is approved.

## Journey

Owner feedback 30 Sep: on the sales portal landing ("Welcome, <name>", the view dropdown that
lists Price Tag Request and Customer asks), a sales agent picks "Conversation" and sees the
WhatsApp conversations of the customers assigned to them. "Customer asks is good, but what if I
want to see the conversation."

## Scope

- New landing kind `conversation` next to `customer_asks`, same picker, same toolbar conventions.
- Reuse the existing thread component (`components/common/RespondChatList`), as the ticket drawer
  and the SLA detail page already do through `TicketConversationPanel`.
- Scope to the customers assigned to the logged-in salesman. Assignment mechanics: see the
  "Findings" section (filled in as the code is read).

## Findings

(filled in with file:line as the code is read)

## Open questions for the owner (settled on the mock)

1. Read-only vs reply.
2. List sorting.
3. Card vs list.

## Mock

`documentation/plans/sales/mockups/sales-conversation-30sep-mockup.html` (one self-contained
static HTML file, in the app's design system).
