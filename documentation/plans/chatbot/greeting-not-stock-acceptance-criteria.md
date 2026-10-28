# UAC: greeting-not-stock

Plan: `PLAN-greeting-not-stock.md`. Tests: `sorento_crm_backend/tests/chatbot/test_greeting_not_stock.py`.

- AC-1: "Hi" from a contact whose profile remembers a usual product, with nothing open, is
  answered on the `low_signal` lane even when the parser reads it as a stock ask for that
  product. No tool is called and the reply is not a stock summary. The trace carries a
  `context_ask_dropped` event.
- AC-2: "eta?" from the same contact is answered on `business_query` for the remembered
  product (memory still fills the slot of a real ask).
- AC-3: greetings, thanks, acknowledgements and emoji-only messages in English, Malay and
  Chinese count as no business content; any word off the list, any question mark,
  punctuation alone and an empty message do not ("got?", "terima?", "??", "ok?").
- AC-4: nothing is dropped while the bot waits on something: an open pick or offer, a required
  ask, an open idea draft ("ok" still confirms it in the ideate lane), or a question the focus
  holds. A quoted reply and a photo are never touched.
- AC-5: a dropped ask also drops the parser's declared `state_changes`, so the carried focus is
  left exactly as it was.
