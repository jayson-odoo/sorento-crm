# PLAN: ticket resolving reply-to (quoted message) with WhatsApp gestures (#1317)

Status: Track: full (FE diff over 300 lines with tests; no migration, no auth/RBAC change, no new ingest surface). Built and reviewed on PR #1318 (reviewer: no blockers, 3 should-fix applied). Fix lane round 2 (owner answers 28 Sep): menu and swipe on every conversation surface through one shared bubble component, compact quote (AC-RT-6 revised, AC-RT-6b); awaiting CI label and owner hand test. Browser pass not run in the cloud lane (needs a Respond-linked ticket on prod-copy data; see cloud-lanes.md "What stays local").
UAC: `ticket-reply-to-27sep-acceptance-criteria.md`
Issue: #1317. Owner's words there are the scope: bring back reply-to in ticket resolving, WhatsApp gestures (swipe right on the phone, chevron or right click on desktop), carried in the outgoing text the way the dropped version did.

## Journey

See the UAC's Journey section (one copy). In one line: staff answering several concurrent
escalations for one contact picks the customer message they are answering (chevron / right click
on desktop, swipe right / long press on the phone), sees a quoted preview above the composer,
sends, and both the customer's handset and the CRM thread show which message the answer is for.

## Archaeology (the dropped implementation)

The owner remembers the wire format as "`|{replyTo}` followed by a new line". Git says the shipped
convention was a `>` quote line, and that is what this plan restores:

- **Added** in `e91b225ce` (12 Aug 2026, "conversation intervention tickets - Phase 1", squashed into
  `ac6b2fc4a` / PR #137). `lib/respondIoChatRender.ts` (at `e313ac690^`, lines 234-297):
  - `QUOTE_LINE_PREFIX = '> '`, `QUOTE_EXCERPT_MAX_CHARS = 160`
  - `buildQuotedReplyText(quotedText, body)`: collapse whitespace in the excerpt, clip to 160 chars
    plus `…`, return `` `> ${clipped}\n${body}` ``. Empty excerpt returns the body unchanged.
  - `splitQuotedPrefix(text)`: leading `>` lines become `quoted` (prefix stripped), the rest is
    `body`.
  - `splitMessageQuote(item)`: direction rule, only OUTGOING text is split.
- **Composer** (`SharedConversationComposer.tsx` at `e313ac690^`): `replyTo` / `onClearReplyTo`
  props; `handleSend` line 365 `replyTo?.excerpt ? buildQuotedReplyText(replyTo.excerpt, typed) : typed`;
  a `composer-reply-to` chip (line 463) with the excerpt and a "Cancel reply" X; `sendAdapter` got
  `replyToMessageId` / `replyToExcerpt`.
- **Bubble** (`RespondChatList.tsx` at `e313ac690^`): `onReply` prop (line 98), a small "Reply" text
  button in the sender row (line 785), and the quoted block rendered from `splitMessageQuote`
  (line 716) as an italic `border-s-2 border-emerald-500` strip.
- **Excerpt** (`components/common/conversation/quotedReply.ts`): the message text, else `[type]`.
- **Fix** `7b18bbb72` (13 Aug): the prefix was being stripped from INBOUND messages too, eating a
  contact's own leading `>` lines. Fixed by the direction rule. This is the only thing the
  convention ever broke, and the rule is kept.
- **Dropped** in `e313ac690` (16 Aug, "remove the outbound reply-to emulation", docs in
  `73337939a`): "Respond exposes no reply-to for API sends (403 on the raw-payload path), so our
  outgoing `> quoted line` was theatre: it rendered on screen like a real quote reference and was
  not one." Nothing was broken; it was dropped because it is not a native WhatsApp quoted reply.
  The owner now wants it back regardless (#1317), because the customer and the staff cannot trace
  answers across concurrent escalations without it.
- **Still on main** (backend, untouched by the drop): `app/api/v1/sla/sla_tracking.py:1438-1493`
  still accepts optional `reply_to_message_id` / `reply_to_excerpt` on JSON and multipart;
  `app/services/sla_service.py:6569-6570` threads them through, `:6584-6586` documents that `text`
  "is expected to already carry the composer's `>`-quote prefix", and `:6668-6671` writes them into
  the response-clock event reason (`reply_to_message_id=<id>`, `quoted_reply=true`). So the backend
  needs no change; a contract test pins it.
- The ticket send path is `POST /{tracking_id}/ticket/send` -> `send_ticket_message` ->
  `_deliver_conversation_message` -> `RespondClient.send_message` (not the n8n
  `sorento-sub-respond-sendmsg` sub-workflow, which is the chatbot's lane). The text is delivered
  verbatim.

**Wire format reused, not reinvented:** `> {excerpt}\n{body}`. WhatsApp itself renders a leading
`> ` line as a quote block (2024 formatting), so the customer sees a quote-shaped line above the
answer.

## Current surface (read, main at 52b0ac24)

- `TicketConversationPanel.tsx` (the ticket resolving conversation, mounted by the worklist drawer
  and the SLA "Chat Records" sheet): `RespondChatList` at :238, Reply / Comment tabs at :283-310,
  `SharedConversationComposer` at :336 with Attach, Voice, Snippet, AI assist, Send template,
  `sendAdapter` at :367 sending `{text, attachments}`.
- `RespondChatList.tsx`: bubble at :1045-1112, inbound structured quote `QuotedContextBlock`
  :433-486, local jump `jumpToMessage` :813-819, flash ring :1011.
- `interventionTicketService.ts` `sendInterventionTicketMessage`: JSON `{text}` or multipart
  `text, files[]`.

## Design

1. **Wire format helpers** back in `lib/respondIoChatRender.ts`: `QUOTE_LINE_PREFIX`,
   `QUOTE_EXCERPT_MAX_CHARS`, `buildQuotedReplyText`, `splitQuotedPrefix`, `splitMessageQuote`
   (verbatim from `e313ac690^`), plus `quoteExcerptOf(item)` (body text, else the attachment
   placeholder, else `[type]`) and `findQuotedOriginal(excerpt, earlier)` (newest earlier message
   whose collapsed text starts with the excerpt minus its `…`).
2. **Bubble menu** on every bubble of every thread surface (round 2, owner answer 3; AC-RT-6
   revised): `MessageBubbleActions` is the one bubble wrapper for `RespondChatList` and
   `ChatTranscript`; each surface with a composer owns its target via `useReplyTarget`.
   `components/ui/context-menu` wraps the bubble (right click; touch long press is Radix's own),
   `components/ui/dropdown-menu` behind a chevron-down at the bubble's top-end corner, visible on
   `group-hover` / focus under `(hover: hover)`. Items: Reply (when `canReply`), Copy. One
   `MessageActionItems` list feeds both menus.
3. **Swipe** as a small hook `useSwipeToReply` (pointer events, `pointerType === 'touch'` only,
   10px direction-lock slop, 56px threshold, 80px cap, `touch-action: pan-y`). Pure
   `swipeOffset(dx)` / `swipeTriggers(dx)` exported for tests. Transform is written inline;
   snap back is a `transform` transition on `--duration-fast` / `--ease-standard`, none under
   reduced motion.
4. **Quote rendering**: outgoing bubbles split through `splitMessageQuote`; the quoted part renders
   in the existing `QuotedContextBlock` (same look as an inbound quote, "Replying to {sender}"),
   sender and jump target from `findQuotedOriginal` over the loaded messages before it. Structured
   inbound `replyTo` wins when both exist.
5. **Composer**: `replyTo` / `onClearReplyTo` props back on `SharedConversationComposer`; preview
   shows sender + 2-line clamp + "Cancel reply"; `handleSend` composes with
   `buildQuotedReplyText`; `sendAdapter` receives `replyToMessageId` / `replyToExcerpt`; cleared on
   success; textarea focused when a target is set.
6. **Panel**: `TicketConversationPanel` owns `replyTarget` state; Reply from the menu sets it and
   switches to the Reply tab; the preview only renders in Reply mode; a ticket change clears it.
   `interventionTicketService` sends `reply_to_message_id` / `reply_to_excerpt` on both lanes.

No backend change, no migration (alembic heads quoted in the PR close-out).

## Grill (posted on #1317; the build assumes the bold answers)

1. Wire format: the owner remembers `|{replyTo}`; history shows `> {excerpt}\n{body}`. **Reuse the
   shipped `>` convention (WhatsApp renders it as a quote); do not invent `|{...}`.**
2. Quote length: **160 characters, whitespace collapsed, then `…` (as shipped).**
3. Which surfaces get the menu: **only the ticket resolving conversation (drawer + Chat Records
   sheet); the quoted block renders on every thread surface because it is the same message.**
   Owner (28 Sep): every place a conversation is shown. Round 2 applies it.
4. Menu items: **Reply and Copy only.**
5. Comment tab: **a quote never goes into an internal comment; the preview hides on Comment and
   returns on Reply.**
6. Swipe feel: **56px threshold, 80px cap, haptic tick (where the phone supports it) on crossing
   the threshold, snap back otherwise.**
7. Quoting our own (outgoing) messages: **allowed, as in WhatsApp; the sender reads as the agent
   name or "Sorento".**
8. Tap on a quote whose original is not in the loaded page: **a plain label (no id travels in
   the text to fetch it by); scroll up loads older pages and the quote becomes tappable once the
   original is loaded.**

## Review round 1 (applied)

- Out of the 24h window the send is a template and line breaks are flattened, so the quote and
  the answer arrive on one line (`> quote answer`). The quote is kept (the customer still sees
  which message is answered) and the composer's one-line warning now shows whenever a quote is
  present (AC-RT-17).
- The post-send clear names the target it sent (`onClearReplyTo(sent)`), so a bubble picked
  while a send was in flight stays picked.
- AC-RT-8 boundary: a release at exactly 56px replies (test added; `>=` to `>` now goes red).
- The swipe arrow rides just outside the bubble's leading edge instead of the row's start.

## Tests (red first)

- vitest `lib/respondIoChatRender.replyto.test.ts`: build/split round trip, 160 clip, direction
  rule, excerpt placeholder, `findQuotedOriginal`.
- vitest `components/common/RespondChatList.replyto.test.tsx`: chevron menu items (AC-RT-1),
  context menu (AC-RT-2), Copy (AC-RT-4), Copy only when `canReply` false (AC-RT-5), no menu
  without `onReply` (AC-RT-6), swipe past threshold fires / short snaps back / mouse ignored /
  vertical ignored (AC-RT-7..10), quote block rendered not raw (AC-RT-20), sender + tap scroll
  (AC-RT-21/22), structured wins (AC-RT-23).
- vitest `SharedConversationComposer.replyto.test.tsx`: preview + dismiss + composed text + audit
  fields + clear on success (AC-RT-13/14/17/19).
- vitest `TicketConversationPanel.replyto.test.tsx`: Reply switches tab, preview hidden on Comment
  (AC-RT-3/16).
- vitest `interventionTicketService.test.ts`: `reply_to_*` on JSON and multipart.
- pytest `tests/test_intervention_ticket_send_route.py`: outgoing text shape verbatim + audit
  reason (AC-RT-18). Expected green on first run: the backend already carries this contract; the
  test pins it.
