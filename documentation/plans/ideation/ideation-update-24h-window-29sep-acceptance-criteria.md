# UAC - Ideation status update joins the 24h-window-aware update sender

Plan: `PLAN-ideation-update-24h-window-29sep.md`. `[BE][T]` = backend, covered by a pytest.

- **AC-UW001** `[BE][T]` An ideation status event for a requester whose 24h window is OPEN sends
  one free-text session message through `RespondClient.send_message`, never the template.
- **AC-UW002** `[BE][T]` The same event for a requester whose window is CLOSED sends the mapped
  approved template through `RespondClient.send_template_message`, never free text.
- **AC-UW003** `[BE][T]` When the window cannot be determined (no Respond.io data and no chat
  history), the template is sent. This is the same default the form update flow gets from
  `get_window_state`, asserted through that real function.
- **AC-UW004** `[BE][T]` The session text names the idea number, the new status and the track
  link. With a known contact name it opens `Hi <name>, `; with no name it has no greeting and never
  reads `Hi -`.
- **AC-UW005** `[BE][T]` The event's `integration_logs` row carries the attempted payload: a
  `text` message block inside the window, a `whatsapp_template` block outside, plus
  `event.sent_as` and `event.window` so the Respond outbox shows which path ran.
- **AC-UW006** `[BE][T]` Window open and no template mapped: the session text is still sent and
  logged `success`. Window closed and no template mapped: logged `skipped` / `NO_TEMPLATE`.
- **AC-UW007** `[BE][T]` Idempotency is unchanged: a redelivered event is not sent twice, one row
  per `event_id`.
- **AC-UW008** `[BE][T]` Every other caller of `send_text_or_template` behaves exactly as before
  (the new keyword defaults to the current rendering).
