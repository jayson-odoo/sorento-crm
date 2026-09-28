# UAC - Ideation status update send (issue #1355)

**Status:** in build, 29 Sep 2026
**Plan:** `PLAN-ideation-status-update-29sep.md` (this file is the contract it fulfils)

Tags: `[BE]` sorento backend, `[FE]` sorento frontend, `[T]` pinned by a test.

## Journey

Actor: a business user who submitted an idea over WhatsApp (the requester). Their idea moves on
the shared-service board (a stage change, a merge into another idea, or a separation from one).
Within about a minute they receive the approved "ideation status update" WhatsApp template naming
their idea, the new stage and the track link. A test idea never messages anyone. The owner sees
one integration log row per event, send or skip, with the reason.

## Template use case

- **AC-IS001** `[BE][T]` `ideation_status_update` is in `TEMPLATE_DEFAULT_USE_CASES`, so
  `GET /integrations/respond/template-defaults` returns a row for it and `set_default` accepts it.
- **AC-IS002** `[FE][T]` The WhatsApp templates screen lists "Ideation - Status Update" (status
  update group), and the mapping dropdown offers "Idea number", "New status label" and "Track
  link"; "Track link" is also offered for a URL button.

## Poller and cursor

- **AC-IS010** `[BE][T]` A tick calls `GET {base}/ideation/intake/status-events` with
  `after=<cursor>`, `limit=100`, `includeTest=true` and `Authorization: Bearer <workspace key>`,
  the same base URL and key as `create-idea`.
- **AC-IS011** `[BE][T]` Events are handled in ascending `seq` even when the feed returns them out
  of order.
- **AC-IS012** `[BE][T]` After each handled event the cursor equals that event's `seq`, committed
  with its log row.
- **AC-IS013** `[BE][T]` If an event's handling cannot be recorded (the log write fails), the
  cursor stays on the last handled event and the tick stops without raising.
- **AC-IS014** `[BE][T]` A feed outage (transport error or non-2xx) leaves the cursor unchanged,
  sends nothing, and does not raise.
- **AC-IS015** `[BE][T]` No base URL or key configured: the tick does nothing.
- **AC-IS016** `[BE][T]` The cursor is keyed by the feed base URL; a different base URL starts
  from its own cursor.
- **AC-IS017** `[BE][T]` The scheduler registers `ideation_status_events_poll` at 60 s.

## Kinds

- **AC-IS020** `[BE][T]` `status_changed`: the template goes with `idea_number` = the idea number,
  `status_label` = the new status label, `track_url` = the track link.
- **AC-IS021** `[BE][T]` `merged`: `status_label` = "combined with <merged_into.idea_number>",
  naming the survivor.
- **AC-IS022** `[BE][T]` `unmerged`: `status_label` = "handled separately again from
  <separated_from.idea_number>, now <status_label>".
- **AC-IS023** `[BE][T]` No `idea_number`: `idea_number` falls back to `idea_title`.
- **AC-IS024** `[BE][T]` An unknown `kind` is logged `skipped` / `UNKNOWN_KIND`, nothing sent, the
  cursor advances.

## Idempotency

- **AC-IS030** `[BE][T]` A redelivered `event_id` (same event in a later page, or the cursor
  rewound) sends nothing and writes no second log row.
- **AC-IS031** `[BE][T]` The database refuses a second `ideation_status_events` log row for the
  same `event_id` (partial unique index).

## Guards

- **AC-IS040** `[BE][T]` `is_test` true: never sent, logged `skipped` / `IS_TEST`, even when the
  requester is a known, opted-in contact with a mapped template.
- **AC-IS041** `[BE][T]` Requester opted out (`outbound_enabled` false): not sent, logged
  `skipped` / `OPTED_OUT`.
- **AC-IS042** `[BE][T]` No `respond_contacts` row for `requester_phone` (or no Respond.io id):
  not sent, logged `skipped` / `UNKNOWN_CONTACT`.
- **AC-IS043** `[BE][T]` `requester_phone` matches a contact by digits when the formatting differs.
- **AC-IS044** `[BE][T]` No `requester_phone`: logged `skipped` / `NO_REQUESTER_PHONE`.

## Template only, never free text

- **AC-IS050** `[BE][T]` The send goes through `send_template_for_use_case` to
  `RespondClient.send_template_message` with the mapped approved template, and never through
  `send_message` (free text), whether or not the requester's 24h window is open.
- **AC-IS051** `[BE][T]` No valid mapping: logged `skipped` / `NO_TEMPLATE` with the reason, the
  poller goes on to the next event and does not raise.
- **AC-IS052** `[BE][T]` A Respond.io send error: logged `failed` / `SEND_FAILED`, the cursor
  advances, later events are still handled.

## Log rows

- **AC-IS060** `[BE][T]` A send writes one row: `integration_channel='respond_io'`,
  `business_table='ideation_status_events'`, `business_id=<event_id>`,
  `external_reference=<idea number>`, `endpoint='ideation_status_update'`, `status='success'`,
  `request_payload` carrying `event_id`, `kind`, `idea_number`, `template`, `parameters`.
- **AC-IS061** `[BE][T]` A skip writes the same shape with `status='skipped'` and `error_code` =
  the reason, and `template` = the mapped template name or null.
- **AC-IS062** `[BE][T]` No row is ever written `pending` or `processing`, so the integration-log
  retry sweeper never picks one up.

## Migration

- **AC-IS070** `[BE][T]` The migration creates `ideation_status_event_cursors` and the partial
  unique index, is idempotent on a database that already has them, and downgrades cleanly.
