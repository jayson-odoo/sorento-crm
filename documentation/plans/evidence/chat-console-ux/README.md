# CHAT-CONSOLE-UX browser evidence (20 Oct 2026, sandbox)

agent-browser 0.27.0 over CDP to the sandbox Chromium started with
`--use-fake-device-for-media-stream --use-fake-ui-for-media-stream` (a real MediaRecorder
recording a synthetic tone). `next dev` (StrictMode on), sandbox backend on a throwaway
`*_ci` Postgres, signed in as the never-stuck smoke admin.

Deviations, stated: the page was opened by URL, not by sidebar clicks (the empty sandbox DB
leaves the System sub-groups empty for the smoke admin; this lane changes no nav config). The
console turn endpoint was stubbed in-page (`window.fetch` wrapper) so bot bubbles exist without
an LLM; every request body was captured and checked. Headless Chromium reports `hover: none`,
so the hover chevron is hidden there by the shared component's design; right-click was used.

| File | What it shows |
| --- | --- |
| `cx-1280-replybar.png` | Right-click > Reply: "Replying to Chatbot" bar, caret in the message box |
| `cx-1280-recording.png` | Quoted voice note sent (quote above the player, "Heard: ..."), then the tap-mode bar: Delete, timer, Send |
| `cx-1280-voice-sent.png` | Hold-and-release sends (clips 10 to 12 KB `audio/mp4`) |
| `cx-375-swipe.png` | Touch swipe: bubble follows the finger, reply icon in the gap |
| `cx-375-replybar.png` | Release past the threshold: reply bar, caret in the message box, no horizontal scroll |
| `cx-375-staged-composer.png` | Pasted image staged (thumbnail + Remove) under the quote |
| `cx-375-image-sent.png` | Sent: quote, image, caption in one bubble; POST carried `media.kind=image` and `reply_to` |
| `cx-375-recording.png` | Recording bar at 375 |
| `cx-insecure-mic.png` | `http://<lan ip>:3000` (not localhost): `isSecureContext=false`, mic press toasts "Voice recording needs a secure (https) page." |

Never stuck: a real backend error (unknown contact) at 1280 ended in a toast with the composer
idle; scrollWidth 360 at a 375 viewport (no horizontal scroll).
