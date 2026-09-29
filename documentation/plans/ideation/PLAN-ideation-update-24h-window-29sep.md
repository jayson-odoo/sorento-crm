# PLAN - Ideation status update joins the 24h-window-aware update sender

**Status:** in review, 29 Sep 2026. Track: small fix track (diff under 300 lines, no migration,
no auth or RBAC change, no new ingest surface). Lane `crew/update-24h-unified` (crew lane
UPDATE-24H). UAC: `ideation-update-24h-window-29sep-acceptance-criteria.md`.

## The report

Owner, 29 Sep 2026, production WhatsApp screenshot: the ideation status update (#1357) ALWAYS
sends the approved template ("Hi -, There is an update regarding your recent enquiry ... This is
a system-generated message."), even when the requester had just chatted and is inside the 24h
customer-service window. The form update flow (complaint / stock inquiry / purchase request)
checks the window and sends a session message inside it. Owner: align the behaviour and use one
unified function for this kind of WhatsApp update sending.

## What already exists (read before designing)

The unified function exists and is the choke point every CRM auto-send is documented to use:
`send_text_or_template` in `sorento_crm_backend/app/services/respond_messaging_service.py:571`.

- Window check: `get_window_state` (`respond_messaging_service.py:308`). Source of truth is the
  Respond.io message list; on API error it degrades to `chat_histories`; with NO data it returns
  `open=False`, so the template is the safe default (`_resolve_last_incoming`, line 278). A 23h
  margin (`WINDOW_HOURS`) avoids boundary drops. Cached 45 s per identifier.
- Inside the window: `render_in_window_text` (line 510) renders the use case's template body as
  free text when the template has no URL button (uniformity), else the caller's raw text.
- Outside the window: `send_template_for_use_case` (line 470); no valid mapping raises
  `TemplateSendSkipped`.
- Outbox: every caller writes its own `integration_logs` row and attaches
  `result["request_payload"]` (a `text` or `whatsapp_template` message block), so the Respond
  outbox shows which branch was taken.

The ideation status update was built on `send_template_for_use_case` directly, by design in
`PLAN-ideation-status-update-29sep.md` step 7 ("ALWAYS the approved template, never free text,
window open or not") and pinned by AC-IS050. That decision is what the owner reversed.

## Census of WhatsApp "update" senders (29 Sep 2026)

| Sender | File:line | Window-aware | Action |
| --- | --- | --- | --- |
| Form status updates: complaint, stock inquiry, purchase request, sponsorship form, portal OTP, login OTP, ticket resolved, manual chat message | `app/tasks/respond_io_tasks.py:72` (`_send_and_log`) | yes, via `send_text_or_template` | none (the reference flow) |
| SLA assignment / escalation / daily summary to staff | `app/tasks/notification_tasks.py:168` | yes | none |
| Price tag request updates | `app/services/price_tag_notify.py:173` | yes | none |
| Ideation draft reminder | `app/services/ideation_turn_service.py:1144` | yes | none |
| Stock ask answers | `app/services/stock_ask_service.py:414` | yes | none |
| Procurement (supplier / PO messages) | `app/services/procurement_service.py:7223`, `:9319` | yes | none |
| **Ideation status update** | `app/services/ideation_status_update_service.py:275` | **no: template always** | **this lane: move onto `send_text_or_template`** |
| Manual chat template send (staff picks a template in the chat panel) | `app/services/respond_chat_template_service.py:468`, `:540` | yes, its own branch on `get_window_state` (raw typed text in-window by UAC) | none: staff-driven, behaviour is a product decision |
| Ticket status updates to the submitter | `app/services/ticket_notification_service.py:197`, `:279` | **no** (`send_message` always; a closed window drops the message silently) | follow-up: needs a `ticket_update` template use case first, so behaviour would change |
| Conversation SLA reply (staff-typed) | `app/services/sla_service.py:6099` | no (composer shows the window state and offers the template chooser) | follow-up, staff-driven |
| Activity send (staff-typed) | `app/services/activities_service.py:617` | no | follow-up, staff-driven |
| Portal link send (admin) | `app/services/portal_service.py:362` | no | follow-up, admin-driven |

Only the ideation status update is an automatic update sender off the unified function. The four
"no" rows at the bottom are staff- or admin-initiated free-text sends where the UI itself shows the
window; moving them changes behaviour (a closed window would send a template or fail loudly), so
they stay follow-ups per the brief ("move only where behaviour stays identical").

## The change

1. `respond_messaging_service.send_text_or_template` gains one keyword,
   `render_template_in_window: bool = True`. `False` sends the caller's `text` as-is inside the
   window instead of rendering the template body. Every existing caller is unchanged (default
   `True`). The ideation sender passes `False`: the owner asked for a natural session message
   with the idea number, the new status and the track link, not the template body.
2. `ideation_status_update_service._handle_event` calls `send_text_or_template` with
   `identifier=contact.respond_io_id`, `respond_contact_id=str(contact.id)`,
   `text=<session text>`, `use_case="ideation_status_update"`, `context_vars=...`,
   `render_template_in_window=False`. `TemplateSendSkipped` (window closed, no mapping) is still
   logged `skipped` / `NO_TEMPLATE`; any other error `failed` / `SEND_FAILED` with the attempted
   payload the shared function stamps on the exception.
3. Session text (`build_session_text`): the requester's name from the Respond contact
   (`name`, else `first_name last_name`), never the phone. With a name:
   `Hi Ali, update on your idea IDEA-0010: it is now Discussed. Track it here: <url>`.
   Without: `Update on your idea IDEA-0010: it is now Discussed. Track it here: <url>`.
   Merged / unmerged wording as today. `contact_name` is also added to the template
   `context_vars` so a template slot mapped to it no longer renders "-".
4. Log row: `request_payload` is `result["request_payload"]` (a `text` block inside the window, a
   `whatsapp_template` block outside), and the `event` metadata gains `sent_as` and `window`
   (`open`, `last_incoming_at`, `source`) so the outbox proves which path ran.
5. Idempotency unchanged: one `integration_logs` row per `event_id`, committed with the cursor
   move; the partial unique index still refuses a second row.
6. Docs: the service docstring, `PLAN-ideation-status-update-29sep.md` step 7 and AC-IS050 are
   updated to the new behaviour.

## Tests (pytest, `tests/test_ideation_status_update.py`)

- window open -> `RespondClient.send_message` with the session text; log row `text`, `sent_as=text`.
- window closed -> `send_template_message` with the mapped template; log row `whatsapp_template`.
- window unknown (`_resolve_last_incoming` returns `(None, "none")`, real `get_window_state`) ->
  template. This is the form flow's default too, asserted through the same function.
- name known -> "Hi <name>, ..."; name unknown -> no greeting, no "Hi -".
- window open, no template mapped -> the session text is still sent (no `NO_TEMPLATE` skip).
- window closed, no template mapped -> `skipped` / `NO_TEMPLATE` (unchanged).
- every existing test keeps passing with the fixture's window held closed where it asserted a
  template send.

Safety: the Respond client is monkeypatched in every test; the window tests patch
`get_window_state` or `_resolve_last_incoming`, so no test reaches Respond.io.

## Follow-ups (not in this lane)

- `ticket_notification_service` submitter updates: add a `ticket_update` template use case and
  route through `send_text_or_template` (today a closed window silently drops the message).
- Staff-typed sends (`sla_service:6099`, `activities_service:617`, `portal_service:362`): decide
  whether a closed window should fall back to a template or keep failing visibly in the composer.
