# PLAN - Optimistic send

Status: BUILT + browser-verified 2026-08-26 (pytest 7/7 new + 25 neighbours, vitest 88 across hook/pane/notes; agent-browser evidence below). Uncommitted on feat/external-conversation-comments.
(user decision: build on feat/external-conversation-comments, BE anchor + FE pending bubble).
UAC: optimistic-send-acceptance-criteria.md

## Decision summary

- The thread is read from local `chat_histories`; the fix is to make the CRM's own send write
  the row it already knows about, instead of waiting for Respond -> n8n -> ingest to echo it.
- Dedupe is already solved: `(contact_id, message_id)` partial unique index +
  `persist_messages` pre-probe. The local row is written FIRST; the mirror's upsert then only
  fills nulls (`result`, `turn_id`, `state_trace`).
- One hook point: `ConversationSLATrackingService._deliver_conversation_message` is the funnel
  for both human composers (drawer `ticket/send`, inbox `/{contact_ref}/reply`). Every
  successful Respond acknowledgement inside it is mirrored locally.
- FE stays thin: `useConversationThread` gains `addPending` / `removePending`; each surface
  wraps its `sendAdapter` with add -> send -> refetch -> remove. No react-query cache surgery,
  no reconciliation by id (the BE row is the anchor, the refetch swaps it in).

## Phase 2 - Backend (test-first)

Files:
- `app/services/conversation_thread_service.py`: `mirror_outgoing_send(db, *, identifier,
  respond_contact_id, response, message) -> int`. Resolves the `RespondContact` (by id, else by
  `respond_io_id`), builds one Respond-shaped item (`messageId` from the ack, `traffic`
  `outgoing`, `message` as given), calls `_persist_best_effort`, and on a write publishes
  `conversation_event_bus.EVENT_MESSAGE` for the contact. Never raises.
- `app/services/sla_service.py` `_deliver_conversation_message`: call it after the caption
  send, after each attachment send, and after the text-only send (text or rendered template).
- Tests: `tests/test_outgoing_send_local_mirror.py` (AC-A1..A7) on the pg fixture, patching
  `RespondClient` the way `test_intervention_ticket_send_route.py` does but with a
  timestamp-shaped `messageId`.

## Phase 1 - Frontend (after BE, same branch)

- `components/common/conversation/useConversationThread.ts`: `pendingItems` state;
  `addPending({ text, files })` returns a key; `removePending(key)`; pending items merge into
  `items` in tail mode only, cleared on `resetKey` change. A pending item has no `messageId`,
  `traffic: 'outgoing'`, `status: [{ value: 'pending', timestamp: now }]`, `source: 'pending'`.
- `TicketConversationPanel.tsx` and `ConversationThreadPane.tsx`: wrap `sendAdapter`.
- Tests: `useConversationThread.test.tsx` (add / remove / reset), `ConversationThreadPane.test.tsx`
  (pending bubble is in `items` during the send, gone after).

## Phase 3 - Review + browser evidence

- `/code-review`, then agent-browser run on the dev server: send from the drawer and from the
  inbox, screenshot the clock bubble, then the real bubble.

## Risks / notes

- `_persist_best_effort` commits the session. `log_respond_send` already commits inside the same
  funnel, so this adds no new mid-service commit semantics.
- `sent_at` comes from the Respond id (its clock), matching what the read lane and the mirror
  store, so ordering against the contact's messages is unchanged.

## Evidence run (agent-browser, dev stack, 2026-08-26)

Steps: sign in at `/` -> sidebar SLA Management -> Conversations -> Mine -> Jayson row -> type ->
Send. Then `/` -> My Pending widget -> "Enquiry . Jayson" row (drawer) -> type -> Send.

- Inbox send `optimistic send check 090853`: local row `chat_histories.id=36821`,
  `message_id=1787706536468401`, `ingest_at` 52 ms after Respond's own clock. One bubble in the
  thread at +2.2 s (the Respond round trip finished before the first screenshot, so the clock
  state itself is pinned by the hook test, not the screenshot). Inbox row snippet updated to the
  sent text with "just now".
- Drawer send `drawer optimistic check 091248`: local row `id=36822`, one bubble, same flow.
- The n8n mirror cannot reach the dev DB (it posts to prod), so dedupe on the wild lane is the
  unit test AC-A3 only.
- Found and FIXED in the same change: the thread list opened scrolled to the TOP of a long
  thread (scrollTop 0 of ~22 000 px) on both surfaces, so a fresh bubble landed off-screen. The
  pin-to-bottom effect in `RespondChatList` only scrolled when already within
  `PIN_TO_BOTTOM_SLACK_PX` of the bottom, which a first render of a long thread never is. Now: the
  first non-empty render always lands on the tail (`behavior: auto`), and the reader's own
  pending send always pins (`behavior: smooth`); a contact's message still leaves a reader who
  scrolled up alone. Re-verified in the browser: on open `fromBottom: 0`; after scrolling to the
  top a page prepends and the reader stays put; after own send `fromBottom: 0`.
