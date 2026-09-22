# PLAN: ticket chat panel - one-line enquiry quote, thread fills the sheet, reply-to jump fetches back

Status: review READY, fix round 3 (replyTo.id) pushed, browser B3 re-verify owed (lane `fix/sla-chat-panel-layout`, worktree `sorento_crm-chat-panel-layout`)
UAC: `chat-panel-layout-22sep-acceptance-criteria.md`
Owner rulings (22 Sep 2026): R2 enquiry quote is one line, chat window takes the most space; R3 Chat Records popup thread flex-fills; R4 reply-to jump reuses the search-jump fetch.

## Journey

Staff opens a ticket (worklist drawer or SLA detail "Chat Records"). Today a long quoted enquiry pushes the thread down to a 160px strip, the Chat Records popup caps the thread at 55vh, and clicking "Replying to" on a quote older than the loaded page does nothing. After: the quote is one truncated line with a Show more toggle, the thread fills every pixel the sheet leaves, and the reply-to click scrolls to the quoted message even when it is not yet loaded.

## Defects (`sorento_crm_frontend/`)

1. `app/(protected)/sla-management/conversation-sla-tracking/components/InterventionTicketDrawer.tsx:318-343` renders `ticket.source_message_text` with `whitespace-pre-wrap break-words`, no clamp. `SheetBody` (`:289`) stacks it above `TicketConversationPanel` (`:377-384`, `maxHeightClass="min-h-40 flex-1"`), so the thread shrinks to 160px.
2. `SlaTrackingChatRecords.tsx:88` passes `maxHeightClass={showAsPopup ? 'max-h-[55vh]' : 'max-h-[400px]'}` and never forwards a `className`; the popup mount in `ConversationSLATrackingDetail.tsx:1068-1082` (`Sheet` > `div.flex-1.min-h-0` > `Card`) is not a flex column chain, so the thread cannot grow.
3. `components/common/RespondChatList.tsx:954-957, 998-1004`: `onJump` is set only when the quoted id is in `loadedMessages` (current page). Otherwise `QuotedContextBlock` (`:406-459`) renders an inert div. The search-jump flow already fetches the page around a message id (find it in the same file / `TicketConversationPanel.tsx`; reuse it).

## Fix

1. Enquiry quote: default `truncate` (single line, `title` attr carries the full text) plus a small "Show more / Show less" text button when the text is longer than the line (measure `scrollWidth > clientWidth` or a length threshold; keep it simple). Expanded state uses `whitespace-pre-wrap` with `max-h-40 overflow-y-auto` so even a 2000-char quote cannot push the thread below its floor. Local `useState`, no persistence.
2. Chat Records popup: make the chain flex - `SheetContent` > `SheetBody` `flex min-h-0 flex-1 flex-col` > `Card` `flex min-h-0 flex-1 flex-col` > `CardContent` `flex min-h-0 flex-1 flex-col` > `TicketConversationPanel className="min-h-0 flex-1" maxHeightClass="min-h-40 flex-1"` (same values the drawer uses). Non-popup (inline) mount keeps `max-h-[400px]`. Keep `ChatPanelParity.test.tsx` green (both mounts pass identical feature props; layout props may differ).
3. Reply-to jump: when the quoted id is not loaded, `onJump` is still provided and calls the existing search-jump loader with that message id, then `jumpToMessage` once the page is in. Keep the block a `<button>` in both cases.

## Tests (vitest, write first)

- `InterventionTicketDrawer.test.tsx`: AC-CP-1..3 (one line, toggle, long quote does not change the panel's props / the thread wrapper keeps `flex-1`).
- `SlaTrackingChatRecords.test.tsx`: AC-CP-4..5 (popup mount passes `flex-1` classes, no `max-h-[55vh]`; inline mount keeps `max-h-[400px]`).
- `RespondChatList.quotedcontext.test.tsx`: AC-CP-6..7 (quote outside the loaded window renders a button; click invokes the fetch-back with the quoted id, then scrolls).

## Fix round 3 (browser pass FAIL on AC-CP-B3, real defect)

`lib/respondIoChatRender.ts:53-57` typed `replyTo.messageId` and `describeQuotedContext` (`:331`) read `reply.messageId` - but the LIVE Respond.io relay's `replyTo` carries the quoted message's id as `id`, never `messageId` (verified in the browser: `"replyTo": {"id": 1788922281019104, "message": {...}, "mId": "...", "sender": {...}}`, no `messageId` key at all). Every quote in production rendered as an inert div, including one whose target was in the loaded window. Every test fixture used `messageId`, which is why the suite stayed green. Fixed by reading `reply.id ?? reply.messageId` (the `??` keeps the local `chat_histories` mirror's reconstructed shape working - `conversation_thread_service.py`'s `_row_to_item` still writes `messageId`). Confirmed `conversation_thread_service.py`'s `_respond_item()` passes Respond's raw `replyTo` through untouched for the live "respond" lane - no backend rename, the fix is frontend-only. Note: `persist_messages` in the same backend file (line ~560) reads `reply_to.get("messageId")` too, for the LOCAL search-cache write path - same wrong key, a separate function, flagged but out of this round's scope.

## Browser verification

agent-browser on a lane stack (slot :3083/:8083 currently free, confirm with `lsof` first). Navigate from `/` via sidebar. Evidence: drawer with a 1500-char quote at 1280 and 375 - thread height unchanged; Chat Records popup thread reaches the composer; reply-to click on an old quote scrolls to it. Screenshots to `documentation/plans/sla/evidence/chat-panel-layout/`.

## Out of scope

Backend `source_message_text` content (chatbot lane), keep-assignee (SLA backend lane).
