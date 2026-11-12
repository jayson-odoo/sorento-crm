# PLAN: every trace link opens the turn trace drawer in place (TRACE-SIDEBAR)

Status: implemented, in review (small fix track: FE only, under ~300 lines, no migration, no auth/RBAC change)

## Journey

Owner (11 Nov): "make the trace in chatbot console to open in the sidebar also instead of new tab, similar to
ai assistant panel, anything that click this trace should open on the sidebar".

An admin testing the bot in System > Messaging > Chatbot Console clicks "trace" under a reply. Today a new tab opens
Chat History. After: the shared turn trace drawer (`TurnDetailDrawer`) slides in over the console, the URL and the
console's thread and scroll stay as they were, Escape or X closes it.

## Inventory of trace entry points (main @ 110e494f)

| # | Surface | Where | Today |
|---|---------|-------|-------|
| 1 | Chatbot Console reply "trace" link | `chatbot-console/components/ChatbotConsole.tsx:199` | `<Link target="_blank">` to `chat-history?turn=` (new tab) |
| 2 | Contact > Chatbot > Conversations row | `contacts/[id]/components/ContactChatbotSection.tsx:905` | `rowHref` navigates away to `chat-history?turn=` |
| 3 | AI assistant panel "View trace" | `app/components/common/AIAssistantBubble.tsx:893,1032` | drawer in place (own state) |
| 4 | Chat History turn timeline "Open full trace" | `chat-history/components/TurnPanel.tsx:115,119` | drawer in place (own state); also used by AI prompt DryRunBox |
| 5 | Chat History `?turn=` deep link | `chat-history/page.tsx:95,459` | drawer in place (own state) |
| 6 | AI panel "View trace" on an old (non-routed) reply | `app/components/common/AIAssistantBubble.tsx:902` | `<Link target="_blank">` to the AI usage trace page |
| 7 | AI Usage > Recent queries "View full trace" | `ai-assistant/usage/page.tsx:542` | navigates away to the AI usage trace page |

Chat Overview, Top Asks, Bot Failures (`ReportPage` reports) and Topic Audit render no turn trace link; the AI
wishlist `NoToolAsksCard` uses `turn_id` only as a React key. Nothing to change there.

## Build

- One shared opener: `useTraceDrawer()` (`chat-history/components/TraceDrawer.tsx`) returns
  `{ openTrace, openMessageTrace, traceDrawer }`; every surface above uses it instead of its own `useState` + drawer
  wiring. A chatbot turn opens in `TurnDetailDrawer`; an AI assistant reply (6, 7) opens its `TraceView` in the same
  side drawer shell.
- Closing a `?turn=` drawer drops `turn` from the address, so the same link followed again re-opens it.
- 1 becomes a button calling `openTrace(turnId)`; 2 becomes `onRowClick` calling `openTrace(first_turn_id)`.
- 5 keeps reading `?turn=` and seeds the same opener, so deep links still open the drawer on Chat History.
- Drawer is already `w-full sm:max-w-2xl` (full width on phone).

## Tests (red first)

- `ChatbotConsole.trace.test.tsx`: clicking "trace" opens the drawer (dialog with the turn title), no `window.open`,
  no `target="_blank"` anchor, `router.push` not called.
- `ContactChatbotSection` row click opens the drawer and does not navigate.
- Hook test: `openTrace` opens, Escape closes.

## Standing rules that apply

- "Details, previews ... open in a centred lightbox popup, not ... side panels": the owner's own ask for THIS lane is the
  side drawer (newest ruling wins, and it is the existing shared drawer).
- No UUIDs in UI: drawer title is the short turn number already used today.
