# PLAN: chatbot console composer works like WhatsApp (CHAT-CONSOLE-UX)

Status: Built, in review. Small fix track (no migration, no auth/RBAC change, no new ingest
surface; one backend helper). Crew rulings 20 Oct: Q1 (a) dropdown removed, Q2 (b) a quoted
voice note / image carries the same `reply_to` as text (backend included), Q3 (a) picker stages.

Behaviour card: `chat-console-ux-20oct-behaviour-card.md`. UAC:
`chat-console-ux-20oct-acceptance-criteria.md`. Mock: `chat-console-ux-20oct-mock.html`.

## Scope

One screen: `app/(protected)/system-management/chatbot-console/components/ChatbotConsole.tsx`.
No new message pipeline. Backend: `console_service.py` shares one `_reply_to_block` between the
text envelope and `_run_console_media_turn`, which now receives `reply_to` (Q2 (b)).
Shared fixes found on the way: `useVoiceRecorder` re-arms its unmount flag on (re)mount (React
StrictMode under `next dev` left it set, so no recording ever started there), and
`MessageBubbleActions` stops the closing menu pulling focus back to the bubble after Reply.

## Reuse map

| Need | Existing piece |
| --- | --- |
| Swipe / long-press / hover Reply + Copy | `components/common/conversation/MessageBubbleActions.tsx` (+ `useSwipeToReply.ts`) |
| Replying-to bar above composer | markup of `SharedConversationComposer.tsx:838-865` (`composer-reply-to`) |
| Quote shown on the sent bubble | existing `quotedText` line in `MessageBubble` |
| Recording | `components/common/conversation/useVoiceRecorder.ts` (start/stop/cancel, 2 min cap, mic release) |
| Sending voice / image | `useChatbotConsole().sendMedia(kind, file, caption)`, unchanged |
| Staged image thumbnail + preview | thumbnail chip pattern of `SharedConversationComposer.tsx:655-690`, `AttachmentPreviewModal` |
| Paste | `handlePaste` pattern of `SharedConversationComposer.tsx:594-600` |

## Slices (commits on this lane)

1. Red tests (vitest, jsdom) in `chatbot-console/components/ChatbotConsole.composerUx.test.tsx`
   from the UAC.
2. Swipe/hover reply: bubbles through `MessageBubbleActions`; reply bar; dropdown removed (Q1).
3. Voice: always-visible mic, tap = locked bar, hold = release-to-send, slide-left cancel,
   keyboard Enter/Space starts the bar, every start failure toasted (the secure-context reason
   lives in the component, `voiceUnavailableMessage`). A clip finished mid-turn stages.
4. Paste + staged image (and picker staging, Q3).
5. Q2 (b): `reply_to` on the media POST, on the pending-poll follow-up turn and on Retry;
   backend media envelope (`tests/chatbot/test_console_media_reply_to.py`).
6. Reviewer, browser pass 1280/375 in sandbox, hand-test script.

## Out of scope / follow-ups

- HTTPS on the tailnet host: owner-run `tailscale serve`, see behaviour card.
