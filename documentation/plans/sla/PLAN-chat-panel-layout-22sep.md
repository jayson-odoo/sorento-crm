# PLAN: ticket chat panel - one-line enquiry quote, thread fills the sheet, reply-to jump fetches back

Status: review READY, browser B3 PASS, 375 overlap fix pushed, re-verify owed (lane `fix/sla-chat-panel-layout`, worktree `sorento_crm-chat-panel-layout`)
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

## Fix round 4 (AC-CP-B3 PASS; new 375px overlap defect on the SAME run)

At 375x812, ticket ac2e3912 (Niki) opened via `/?ticket=<id>`, reproduced twice on a fresh load: the message thread's text rendered on top of the composer's "Outside the 24h window - this is sent as the template..." text, at the same y. DOM probe: one `.overflow-y-auto` measured `scrollHeight 12793`, `clientHeight 158` - the thread's own scroll box (`min-h-40` floor, `RespondChatList.tsx:875`) is correctly clipping and scrolling its OWN content; that box is not the defect.

Diagnosed against `origin/main` first: `SheetContent`'s className (`overflow-y-auto`, explicit at the call site) and `SheetBody`'s (also `overflow-y-auto`, from `sheet.tsx`'s own base class) are BOTH unchanged since main - the double-scroll-container structure (reviewer's S3 candidate) is pre-existing, not introduced by this lane. What IS new in this lane is the enquiry quote now being one line (freeing space) and the flex-fill wiring this PLAN's own R2/R3 fixes rely on - neither explains the overlap on its own, and the composer/tablist have never carried `shrink-0`, on main or here.

Fixed at the smallest seam, in the two files this lane already owns:
1. `InterventionTicketDrawer.tsx` and `ConversationSLATrackingDetail.tsx`'s Chat Records `Sheet`: `SheetContent`'s className changed from `overflow-y-auto` to `overflow-hidden` - `SheetBody` is the ONE intended scroll container (its own docstring says so), and `SheetContent` sits at a fixed `h-full`, so it never needs to scroll on its own; letting it stay independently scrollable gave the layout two competing scroll contexts around the same flex-fill thread.
2. `TicketConversationPanel.tsx` (shared by both surfaces): the Reply/Comment mode-switch bar gets `shrink-0` directly; `InternalCommentComposer` and `SharedConversationComposer` (neither accepts a `className`) are each wrapped in a `<div className="shrink-0">` - neither carried a shrink floor before, on main or here, so a squeeze anywhere upstream had nowhere safe to land.

Vitest cannot measure real layout (jsdom's `scrollWidth`/`clientHeight` are always 0), so the new tests pin the STRUCTURE: `SheetContent`'s rendered className never contains `overflow-y-auto`, and the composer / mode-switch DOM carries a `.shrink-0` ancestor. Confirmed red before the fix, green after.

## Browser verification

agent-browser on a lane stack (slot :3083/:8083 currently free, confirm with `lsof` first). Navigate from `/` via sidebar. Evidence: drawer with a 1500-char quote at 1280 and 375 - thread height unchanged; Chat Records popup thread reaches the composer; reply-to click on an old quote scrolls to it. Screenshots to `documentation/plans/sla/evidence/chat-panel-layout/`.

## Out of scope

Backend `source_message_text` content (chatbot lane), keep-assignee (SLA backend lane).
