# PLAN: ticket chat panel - one-line enquiry quote, thread fills the sheet, reply-to jump fetches back

Status: small fix track, review READY (5 rounds), browser PASS B1/B2/B3 at 375 + 1280, PR #1133 awaiting merge go (lane `fix/sla-chat-panel-layout`, worktree `sorento_crm-chat-panel-layout`)
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

**Round 4's fix did not actually stop the overlap** - see Fix round 5 below.

## Fix round 5 (375 re-verify still FAILS on af6c7f0ca; round 4 was incomplete)

Measured rects on a fresh load, drawer at 375x812: tablist `{top 350.9, bottom 392.9}`, thread scroll box `{top 358, bottom 518}` (height 160 = `min-h-40`, `scrollHeight 12793`), composer `shrink-0` wrapper `{top 404.9, bottom 772}`. The composer's rect did not move on scroll - this is a layout defect, not a scroll one.

The floored inner scroll box (`RespondChatList.tsx`'s `chat-scroll-container`, `min-h-40` via `maxHeightClass`) was never the problem - its OWN box correctly renders at 160px, per round 4's own measurement. The actual defect: its ANCESTORS carry no floor of their own - `RespondChatList`'s root (`relative flex min-h-0 flex-1 flex-col`) and `TicketConversationPanel`'s root (`min-h-0 flex-1`, as passed by the caller). A per-element CSS `min-height` on a deeply nested child does NOT enlarge an ancestor's computed flex size - so under pressure the outer flex algorithm squeezes those floor-less ancestors to near-zero (~35-42px, matching the gap between `tablist.top` and where the panel's own box would start), and the floored 160px scroll box overflows that squeezed ancestor, painting over the tablist and composer laid out after it in the column.

Fixed by putting the SAME floor on every flex item in the chain, not only the innermost box:
1. `RespondChatList.tsx`: new optional `className` prop, applied to the component's own root via `cn('relative flex min-h-0 flex-1 flex-col', className)`. Every OTHER caller (Complaint/StockInquiry/PurchaseRequest panels, the Conversations inbox, the portal ticket-draft page) passes nothing, so this is a no-op for them.
2. `TicketConversationPanel.tsx`: forwards its own `className` prop down to `RespondChatList`'s new `className` too, so both roots always carry the identical value.
3. `InterventionTicketDrawer.tsx` and `SlaTrackingChatRecords.tsx` (popup mode): the `className` passed to `TicketConversationPanel` changed from `"min-h-0 flex-1"` to `"min-h-40 flex-1"` - the SAME value already passed as `maxHeightClass`. The inline (non-popup) mount passes no `className` at all, unaffected (fixed `max-h-[400px]`, not a flex-fill scenario).

AC-CP-3 and AC-CP-5 updated to match (the panel's `className` is now `"min-h-40 flex-1"`, not `"min-h-0 flex-1"`). New vitest in `InterventionTicketDrawer.test.tsx` pins that `RespondChatList` receives the floor via its own `className` prop (not only `maxHeightClass`), and that `TicketConversationPanel`'s root carries `min-h-40` rather than `min-h-0`. Confirmed red before the fix (reverted the drawer's `className` back to `min-h-0 flex-1`), green after. Also added an assertion in `ConversationSLATrackingDetail.gear.test.tsx` pinning the Chat Records `Sheet`'s own `SheetContent` className (round 4's fix there had no test pinning it at all - a prepared, separately-verified addition).

## Fix round 6 (375 re-verify on b94356ef3: improved, still a 41px overlap)

Rects on re-verify: thread scroll box `{358, 518}` (height 160), tablist `{477, 519}`, composer `{531, 898}`. `tablist.bottom <= composer.top` now holds (round 5's `shrink-0` fix works) and `SheetBody` scrolls (777 vs 675) with the composer reachable - but `thread.bottom` (518) is 41px past `tablist.top` (477).

Reading the numbers: the `RespondChatList` root is now ~160px tall (top ~318 to 477), correctly honouring round 5's new floor. But that root ALSO contains its OWN header/search chrome (contact avatar/name row, ~40px, top 318 to 358) ABOVE the inner scroll box - and the inner scroll box (`RespondChatList.tsx`'s `chat-scroll-container`) STILL carries its own `min-h-40` too. Two floors for the same 160px requirement, nested inside each other: chrome (40) + inner-box-floor (160) = 200px of REQUIRED height inside a root whose OWN floor is only 160px total. The inner box wins its own min-height fight (it renders its full 160px, 358 to 518) and overflows the root's bottom edge (477) by exactly the chrome's height (41px ≈ the 40px chrome), painting over the tablist.

Fixed by removing the floor from the INNER box - the root already carries the equivalent floor, and the inner box only needs to grow (`flex-1`) into whatever the root leaves it after the chrome:
1. `InterventionTicketDrawer.tsx`: `maxHeightClass="min-h-40 flex-1"` → `maxHeightClass="min-h-0 flex-1"` (the `className="min-h-40 flex-1"` from round 5 is unchanged - the root floor stays).
2. `SlaTrackingChatRecords.tsx` (popup mode): `maxHeightClass={showAsPopup ? 'min-h-40 flex-1' : 'max-h-[400px]'}` → `maxHeightClass={showAsPopup ? 'min-h-0 flex-1' : 'max-h-[400px]'}`. Inline (non-popup) mount and `ConversationThreadPane.tsx`'s `maxHeightClass="max-h-[52vh]"` are untouched (fixed caps, not flex-fill floors).

AC-CP-3/5 (UAC + tests) updated: `maxHeightClass` is now `"min-h-0 flex-1"`; `className` (the root floor, round 5) is unchanged. New `describe` block in `InterventionTicketDrawer.test.tsx` ("fix round 6, one floor not two") pins the inner box's `maxHeightClass` no longer carries `min-h-*`, alongside the root's `className` still carrying `min-h-40`. Confirmed red before the fix (reverted both call sites' `maxHeightClass` back to `min-h-40 flex-1`), green after.

## Browser verification

agent-browser on a lane stack (slot :3083/:8083 currently free, confirm with `lsof` first). Navigate from `/` via sidebar. Evidence: drawer with a 1500-char quote at 1280 and 375 - thread height unchanged; Chat Records popup thread reaches the composer; reply-to click on an old quote scrolls to it. Screenshots to `documentation/plans/sla/evidence/chat-panel-layout/`.

## Out of scope

Backend `source_message_text` content (chatbot lane), keep-assignee (SLA backend lane).

## Follow-ups (not this lane)

Found while diagnosing this lane's defects; none fixed here - each needs its own lane.

1. **Backend: `conversation_thread_service.persist_messages` reads the wrong replyTo key too.** Same bug as fix round 3's frontend fix (`lib/respondIoChatRender.ts`), on the WRITE side: `persist_messages` (`sorento_crm_backend/app/services/conversation_thread_service.py:~560`) does `reply_to.get("messageId")` when persisting a Respond message into the local `chat_histories` mirror (the search-cache write path) - the live relay's `replyTo` carries the id as `id`, never `messageId`. Every quote persisted through this path gets `reply_to_message_id = NULL`, so the LOCAL mirror lane (used for scroll-back search) silently drops quote context that the LIVE "respond" lane (now fixed) renders correctly.
2. **Three feature services each maintain their own local message-item type instead of importing the shared one.** `complaintService.ts`, `stockInquiryService.ts` and `purchaseRequestService.ts` (Complaint / Stock Inquiry / Purchase Request `RespondChatList` mounts) each declare their own `RespondMessageItem` interface rather than reusing `RespondMessageRenderable` from `lib/respondIoChatRender.ts`. `stockInquiryService.ts`'s copy already carries `replyTo.messageId` only (line ~347) - the exact shape fix round 3 fixed in the shared type - so Stock Inquiry's quote blocks likely have the SAME live-relay bug right now. Complaint's and Purchase Request's copies do not declare a `replyTo` field at all yet (no quote capability there today), but the next person to add it will reach for the sibling file's `messageId`-only convention unless these three are pointed at the shared type first.
3. **Five other `SheetContent` mounts pass their own `overflow-y-auto` on top of the primitive's default, alongside a `SheetBody` child.** Same double-scroll-container shape fix round 4 fixed for this lane's two Sheets (`InterventionTicketDrawer.tsx`, `ConversationSLATrackingDetail.tsx`'s Chat Records): `ComplaintDetail.tsx:1378`, `StockInquiryDetail.tsx:1236`, `PurchaseRequestDetail.tsx:1527`, `scm/reorder/components/PlanMethodologySheet.tsx:303`, `project-sales/fulfilment-planning/components/FulfilmentPlanningSheet.tsx:270`. Each is latent until a flex-fill thread (or similarly tall content) is added inside their `SheetBody` at a narrow viewport - not a live defect today, but the same 375px overlap this lane spent five rounds on is one flex-fill change away in any of them.
