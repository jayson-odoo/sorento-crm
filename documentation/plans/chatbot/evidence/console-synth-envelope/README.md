# CONSOLE-SYNTH-ENVELOPE browser pass (cloud sandbox, 8 Nov 2026)

Sandbox stack: throwaway DB `sorento_browse` (copy of the freshly seeded CI DB), seeded by
`harness/seed_browse.py` with one invented superadmin, every module installed, and one invented
respond contact "Simulated Dealer" (respond id 900000777) with NO chatbot turn on record.
Backend uvicorn :8000, frontend `npm run dev` :3000. Reached by sidebar: `/` > System >
Messaging > Chatbot Console. Contact picked from the Contact select, then "MWB248 set" sent.

| Shot | Width | Result |
| --- | --- | --- |
| 01-simulated-badge | 1280 | PASS. No 404 toast. The reply bubble wears "simulated contact, no real WhatsApp history" next to `trace`. |
| 02-simulated-badge | 375 | PASS. Badge wraps under the reply, nothing clipped. |
| 03-ai-replies-off | 1280 | PASS (crew pass fix 2). Same contact with `chatbot_allowed=false`: branch `ai_not_allowed`, the bubble reads "AI replies are OFF for this contact; live, the bot would not answer." instead of "(no reply)". The switch is not bypassed. |

DB after the pass: every turn for 900000777 is `ingress=console`, `is_test=true`,
`envelope.synthetic_envelope=true`, no `message.channel`; zero webhook or non-test rows;
`email_outbox` empty; the turn's only action is `send_message` with `dry_run: true`.
API check: an id with no `respond_contacts` row still answers 404 `CHATBOT_CONSOLE_NO_ENVELOPE`.

The reply text is the "AI service did not answer" fallback because the sandbox DB has no parser
prompt key configured (no LLM was called). The owner hand test on prod-copy data shows a real answer.
