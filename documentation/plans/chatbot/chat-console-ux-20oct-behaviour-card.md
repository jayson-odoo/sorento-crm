# Behaviour card: chatbot console composer works like WhatsApp (CHAT-CONSOLE-UX)

Status: RULED (20 Oct 2026) by crew: Q1 (a), Q2 (b) (NOT the recommendation: a quoted voice
note or image must carry the quote like WhatsApp, the owner answers bot questions by voice), Q3
(a). Small fix track (no migration, no auth change). Plan: `PLAN-chat-console-ux-20oct.md`. Mock:
`chat-console-ux-20oct-mock.html` (same folder).

## Owner report (20 Oct 2026, ~11:20, verbatim)

"I think the reply to mechanism is not so good now. Now I need to choose the message. I think I
need to be able to swipe right to reply just like WhatsApp. Then I will use a lot of voice by then,
so I need a voice to be more intuitive, like WhatsApp, instead of me needing to attach a voice file
or even photo. I need to be able to paste to attach the image instead of I need to choose from the
file picker. Yeah, I need a chat console to be more intuitive to test."

## What happens today (`main` 8ec70c43)

Screen: System Management > Chatbot console
(`app/(protected)/system-management/chatbot-console/components/ChatbotConsole.tsx`).

- **Reply**: a `SearchableSelect` "Reply to" above the composer lists every quotable bubble
  (`ChatbotConsole.tsx:331-343`); the operator picks one by its text. Bubbles have no reply action
  of their own (`MessageBubble`, `:57-159`). The pick rides `sendText` as `reply_to`
  (`:239-253`, `useChatbotConsole.ts:231`).
- **Voice**: a hold-to-record mic exists (`:380-404`, `useVoiceRecorder`), but it is rendered ONLY
  when `voice.available` is true. On the owner's `http://<tailnet host>:3000` URL the browser
  exposes no `navigator.mediaDevices` (microphones need a secure context: https or localhost), so
  the mic is simply absent and the only way to send voice is the paperclip. That is the "attach a
  voice file" the owner describes. Where it does render: a denied permission is never surfaced
  (`voice.start()`'s reason is dropped, `:390`), a finger drifting off the 40px button cancels
  silently (`onPointerLeave`, `:393`), and there is no recording bar.
- **Paste**: none. The textarea has no `onPaste`; a picked file is sent the instant it is chosen,
  with no preview (`handleFilePicked`, `:255-261`).

## The three behaviours

### B1. Swipe right to reply (phone), hover/right-click Reply (desktop)

- Every quotable bubble (a bot reply of a real turn, a customer message the server acknowledged:
  the same set the dropdown lists today, `:226-229`) renders through the shared
  `MessageBubbleActions` (`components/common/conversation/MessageBubbleActions.tsx`), the
  component every other thread surface already uses. That gives, unchanged:
  touch swipe right past 56px replies, haptic tick when armed, snaps back if let go early
  (`useSwipeToReply.ts`); long-press menu Reply / Copy on a phone; a hover chevron and
  right-click menu Reply / Copy on desktop.
- Reply sets the SAME quoted-reply context the dropdown sets today (same `reply_to` payload,
  same `quotedText` on the sent bubble), shows a "Replying to" bar above the composer with the
  quoted text and a Cancel (X), and focuses the message box.
- Greeting lines, a still-pending media status bubble and the user's own unacknowledged bubble
  get no Reply (nothing the backend can quote); Copy still works where there is text.

### B2. Voice like WhatsApp

- The mic button is ALWAYS shown. Tap it: recording starts and the message box is replaced by a
  recording bar (pulsing red dot, mm:ss timer, a Delete button, a Send button).
  Hold it instead: recording runs while the finger is down, release sends, slide left past
  ~80px cancels ("< Slide to cancel" hint in the bar).
- Sent through `sendMedia('audio', file, caption)`, the exact path the paperclip uses for an
  audio file today: same `user-media` bubble with a player, same "Transcribing..." / "Heard: ..."
  bubble, same follow-up turn, same Retry on failure.
- Never stuck: a denied microphone, an insecure page, an unsupported browser, a recorder error
  each end in a toast that says what happened and the composer is back to idle. Recording stops
  itself at 2 minutes and sends (existing cap). Reset or switching contact mid-recording discards
  the clip.

### B3. Paste an image

- Ctrl/Cmd+V (and the phone's long-press Paste in the message box) with an image on the
  clipboard stages it: a thumbnail appears above the message box with a Remove (X); tapping the
  thumbnail opens the shared `AttachmentPreviewModal`. Text pastes are untouched.
- Send then goes through `sendMedia('image', file, caption)`, the same path the picker uses,
  with whatever was typed as the caption. Send is enabled with a staged image and no text.
- One image per send (the console's media turn takes one file): a second paste replaces the
  first.

## Edge cases

| Case | Behaviour |
| --- | --- |
| Mic permission denied | Toast "Microphone access is blocked. Allow it in the browser's site settings and try again."; mic stays enabled so a retry works after granting. |
| http (insecure) page | Toast "Voice recording needs a secure (https) page." ; mic stays visible. |
| Recording, then Reset / contact switch | Clip discarded, mic released. |
| Swipe on a bubble with no Reply (greeting) | Nothing moves (swipe disabled there); vertical scroll unaffected. |
| Send fails (network, 4xx) | Existing toast; the image/voice bubble stays in the thread; an extraction failure offers Retry (quote included) as today. |
| Clip finished while another turn is in flight, or no contact | The clip stages (with a player) and a toast says so; Send sends it. |
| Clipboard holds a non-image file | Ignored (text-only paste behaviour); picker stays for audio files. |
| `sending` is true | Mic and Send disabled as today; paste still stages (sends after). |

## Mobile on the Tailnet URL (http)

- **Works on http**: swipe-to-reply, long-press menu, paste (a `paste` event needs no secure
  context), picker, typing.
- **Does NOT work on http**: the microphone. Browsers expose `getUserMedia` only on https or
  localhost; this cannot be fixed in app code.
- **Smallest fix (no code, owner runs it, I change no infra)**: on the Mac Mini,
  `tailscale serve --bg --https=443 http://localhost:3000` (needs HTTPS certificates enabled
  once in the tailnet admin, DNS > HTTPS Certificates). The phone then opens
  `https://<mini>.<tailnet>.ts.net/` with a real certificate; add that host to
  `NEXT_DEV_ALLOWED_ORIGINS` (`*.ts.net` is already listed in CLAUDE.md's example) and keep
  `AUTH_TRUST_HOST=true`. The `/api/v1` proxy keeps working because browser calls stay relative.

## Questions (at most 3)

- **Q1. Drop the "Reply to" dropdown?** (a) yes, swipe / long-press / hover Reply replace it;
  (b) keep it as a second way. **Recommendation (a)**: two ways to set one quote is the clutter
  the owner is complaining about; desktop keeps hover + right-click.
- **Q2. A quote set, then a voice or image is sent.** The console's media turn does not carry
  `reply_to` today (`console_service.py:461-473`, media branch never receives it). (a) this lane:
  the quote stays set and rides the next TEXT message, voice/image go unquoted; a follow-up lane
  threads `reply_to` through the media turn; (b) widen this lane into the backend now.
  **Recommendation (a)**: keeps this lane UI-only and small; say the word and I open the backend
  follow-up.
- **Q3. The paperclip picker**: (a) a picked file stages with the same preview as a paste, Send
  sends it; (b) keep sending the instant it is picked. **Recommendation (a)**: one behaviour for
  paste and picker, and a wrong pick is removable before it reaches the bot.
