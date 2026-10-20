# UAC: chatbot console composer works like WhatsApp (CHAT-CONSOLE-UX)

Plan: `PLAN-chat-console-ux-20oct.md`. Screen: System Management > Chatbot console.

## Reply

- AC-CX-1. A touch swipe right past the threshold on a quotable bubble (bot reply with a turn,
  acknowledged customer message) sets the reply target; a "Replying to" bar shows its text above
  the composer with a Cancel button.
- AC-CX-2. On desktop each quotable bubble has a "Message actions" control (hover) and a
  right-click menu with Reply; Reply sets the same target as AC-CX-1.
- AC-CX-3. Sending text with a target posts `reply_to` exactly as the dropdown did
  (`{id: turn bubble id, source: 'n8n'}` for a bot bubble, `{id: messageId, source: 'contact'}`
  for a customer bubble), the sent bubble shows the quote, and the bar clears.
- AC-CX-4. Cancel clears the target; nothing is quoted on the next send.
- AC-CX-5. Greeting bubbles offer no Reply.
- AC-CX-6. The "Reply to" dropdown is gone (pending Q1).

## Voice

- AC-CX-7. The mic button renders even when the browser cannot record; pressing it then shows a
  toast naming why (insecure page / unsupported) and the composer stays idle.
- AC-CX-8. Tap (press and release quickly): recording bar with timer, Delete and Send; Send posts
  the clip through `sendMedia('audio', ...)`; Delete posts nothing.
- AC-CX-9. Hold: release after the hold threshold sends the clip; sliding left past the cancel
  distance before release discards it.
- AC-CX-10. A denied microphone shows a toast and returns to idle (no recording bar, mic enabled).

## Paste / attach

- AC-CX-11. Pasting an image into the message box stages it (thumbnail + Remove), sends nothing.
- AC-CX-12. Send with a staged image calls `sendMedia('image', file, typedCaption)` once and
  clears the stage and the draft; Send is enabled with an image and no text.
- AC-CX-13. A text paste is untouched (default behaviour, nothing staged).
- AC-CX-14. Remove clears the staged image.
- AC-CX-15. A picked file stages the same way (pending Q3).

## Never stuck

- AC-CX-16. Every failure above ends in a visible message and an idle, usable composer.
- AC-CX-17. Usable and non-clipped at 375px and 1280px.
