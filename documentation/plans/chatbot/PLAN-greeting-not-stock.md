# PLAN: greeting-not-stock

Status: Build (small fix track: no migration, no auth/RBAC change, no new ingest surface)

## Bug

A bare greeting ("Hi") from a contact with a remembered usual product was sometimes parsed into a
stock ask for that product. The remembered product reaches the parser as context, and the parser
(Gemini flash-lite for staff-tagged contacts) occasionally turns the greeting into a business ask.

## Rule

A message with no business content (greeting, thanks, ok, emoji) never becomes a business ask from
remembered context alone. Remembered products may only fill a slot of a message that IS a business
ask (e.g. "eta?" resolves to the remembered product).

## Fix

Deterministic guard in code (no prompt edit, so no parser eval run and no Gemini spend):
`app/services/chatbot/turn/no_business.py::without_context_ask`, called in `engine.py` right
after `turn_question.without_phantom_answer`. When every word of the message is a greeting,
thanks, acknowledgement or address term (or the message is emoji only), no question is open,
and the turn is neither a quoted reply nor a photo, the verdict is filed as `casual` with every
`apply._IDLE_CHAT_DISQUALIFIERS` key cleared. `apply` then plans no fetch (idle chat) and the
carried focus is left as it was. A `context_ask_dropped` trace event records what was dropped.
Any message with one word off the list ("eta?", a code, a number) reaches APPLY untouched, so a
remembered product still fills an ask's slot.

## Tests

- greeting + remembered product -> greeting reply, no stock ask
- "eta?" + remembered product -> that product
