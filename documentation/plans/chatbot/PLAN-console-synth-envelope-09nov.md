# PLAN: Chatbot Console simulates any contact (synthetic envelope)

Status: in progress (small fix track: under ~300 lines, no migration, no auth/RBAC change, no new ingest surface)
Lane: CONSOLE-SYNTH-ENVELOPE

## Journey

Owner, 9 Nov: picks a contact in the Chatbot Console that has never sent a real WhatsApp
message and types a question. Today the console answers 404 `CHATBOT_CONSOLE_NO_ENVELOPE`
("Send one real WhatsApp message from this contact first"). They just want to simulate.

## Fix

- `console_service._borrow_envelope`: when no real (`ingress='webhook'`, `is_test=false`)
  row exists but a `respond_contacts` row does, return a fresh synthetic base envelope in the
  media-path shape (contact id, phone, firstName, `custom_fields` is_human_intervened=false),
  with NO `message.channel` (the WhatsApp phone gate stays off) and `synthetic_envelope=true`.
- 404 stays only when there is no `respond_contacts` row at all.
- Never borrow a console/test row (S6 rule); synthetic base is built fresh every turn.
- The base still goes through `_build_envelope`, so `is_test` / `test_run_id` keep the
  turn a dry run. Nothing is sent.
- Phone lookup filtered to the default workspace (duplicate `respond_io_id` rows across
  workspaces made `.scalar()` pick an arbitrary one).
- The marker surfaces in the trace summary and the console response
  (`synthetic_envelope`), and the console shows a small badge
  "simulated contact, no real WhatsApp history".

## Tests (see acceptance criteria)

`console-synth-envelope-acceptance-criteria.md`.
