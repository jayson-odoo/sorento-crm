# UAC: ticket chat panel layout

Plan: `PLAN-chat-panel-layout-22sep.md`

## Enquiry quote (InterventionTicketDrawer)

- AC-CP-1 `source_message_text` of 40 chars renders on one line, no toggle.
- AC-CP-2 `source_message_text` of 1500 chars renders as one truncated line with `title` = full text and a "Show more" button; clicking it expands (scrollable, capped height) and the button reads "Show less"; clicking again collapses.
- AC-CP-3 With the 1500-char text expanded, `TicketConversationPanel` still receives `className="min-h-40 flex-1"` and `maxHeightClass="min-h-0 flex-1"` (the thread keeps its flex share; the quote box is height-capped). (Fix round 5: `min-h-40`, not `min-h-0`, on `className` - the floor has to sit on every flex item in the chain, not only the innermost scroll box, or a floor-less ancestor can still be squeezed to near-zero and the floored descendant overflows it. Fix round 6: `maxHeightClass` - the INNER scroll box - does NOT also carry its own `min-h-*`; one floor, on the root, not two - a second equal floor on the inner box overflowed the root by exactly the header/search chrome's height above it.)
- AC-CP-4 Empty `source_message_text` still renders "No enquiry text captured." with no toggle.

## Chat Records popup (SlaTrackingChatRecords)

- AC-CP-5 `showAsPopup` mount passes `TicketConversationPanel` `className` containing `min-h-40 flex-1` and `maxHeightClass="min-h-0 flex-1"`; `max-h-[55vh]` appears nowhere. (Fix round 5/6: see AC-CP-3 - the root floors, the inner scroll box does not.)
- AC-CP-6 Inline (non-popup) mount keeps `maxHeightClass="max-h-[400px]"`.
- AC-CP-7 `ChatPanelParity.test.tsx` stays green.

## Reply-to jump (RespondChatList)

- AC-CP-8 Quote whose message id IS in the loaded window: block is a button; click scrolls to that bubble (existing behaviour, pinned).
- AC-CP-9 Quote whose message id is NOT loaded: block is still a button; click calls the fetch-back loader with that id, and after the page arrives the bubble is scrolled into view.
- AC-CP-10 Quote with no message id (malformed replyTo): inert div, unchanged.
- AC-CP-21 (fix round 3) Quote whose `replyTo` uses the REAL Respond relay wire shape (`id` numeric, `message`, `mId`, `sender` - no `messageId` key at all) with its target IN the loaded window: block is a button; click scrolls.
- AC-CP-22 (fix round 3) Same wire shape, target NOT loaded: `onJumpToMessage` is called with the id as a string.

## Browser (agent-browser, lane stack)

- AC-CP-B1 Worklist drawer, 1280 and 375: ticket with a long quote - thread occupies the space down to the composer; quote is one line with Show more.
- AC-CP-B2 SLA detail > Chat Records: thread reaches the composer instead of stopping at ~55% of the viewport.
- AC-CP-B3 Click "Replying to" on a quote older than the loaded page: view scrolls to the quoted message.
