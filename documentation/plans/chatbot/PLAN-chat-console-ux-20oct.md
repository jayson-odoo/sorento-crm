# PLAN: chatbot console composer works like WhatsApp (CHAT-CONSOLE-UX)

Status: Planned, small fix track (FE only, no migration, no auth/RBAC change, no new ingest
surface). Awaiting owner on behaviour card Q1-Q3.

Behaviour card: `chat-console-ux-20oct-behaviour-card.md`. UAC:
`chat-console-ux-20oct-acceptance-criteria.md`. Mock: `chat-console-ux-20oct-mock.html`.

## Scope

One screen: `app/(protected)/system-management/chatbot-console/components/ChatbotConsole.tsx`.
No new message pipeline, no backend change.

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
   every start failure toasted. `useVoiceRecorder` gains a `secure-context` reason (one string).
4. Paste + staged image (and picker staging, Q3).
5. Reviewer, browser pass 1280/375 in sandbox, hand-test script.

## Out of scope / follow-ups

- `reply_to` on a media turn (backend, Q2 option (b)).
- HTTPS on the tailnet host: owner-run `tailscale serve`, see behaviour card.
