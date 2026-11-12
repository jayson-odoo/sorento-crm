# PLAN: N8N-RETIRE-A, the CRM sends bot replies (phase A of N8N-DECOM-HA)

Status: Build (tests first). Behaviour card answered 12 Nov (section 0). Track: L, LEAD
pattern (tester, then coder, then reviewer + security-reviewer). Parent:
`documentation/plans/infra/PLAN-n8n-decom-ha-01nov.md` section 4 stage 2, job J1 (section 2).
UAC: `n8n-retire-a-bot-reply-acceptance-criteria.md` (this folder).

Owner, 1 Nov: retire n8n; Q1 (a) staged, each CRM job switched on beside n8n alone. Owner, 11 Nov:
every failed external send is retryable. Crew never flips the switch and never touches an n8n
workflow; the owner does both.

## 0. Behaviour card answers (crew, 12 Nov, from owner rulings 1 Nov + 11 Nov)

- Q1 (b): the switch is `n8n` (default) / `CRM for listed contacts` / `CRM for all`, with its own
  contact list, so the owner tests on his own number first.
- Q2 (a): a part with an unknown outcome is looked up in the conversation's message list first:
  found = sent (locked), not found = sent again, lookup fails = "Not confirmed" + Try again.
- Q3 (a): Try again re-sends only the parts not yet confirmed, same words.
- Q4 (a): respond.io's documented quick-reply message type; fakes in tests; proven at the owner's
  stage-2 own-number test.
- Q5 (a): one writer for the outgoing chat row (the `message.sent` webhook), linked to the turn by
  the respond.io message id the send returns.

## 1. What happens today (measured from the code)

1. A covered contact's message (direct ingress `contacts` / `all`,
   `app/services/chatbot/direct_ingress.py:139-142`) is queued in the CRM inbox queue and answered
   by the drain (`app/services/chatbot/inbox_queue.py:948` `_run_row`).
2. The drain hands the finished actions to `_post` (`inbox_queue.py:718-747`), which stamps the
   row `sending`, splits long replies (`engine.split_send_actions`, `engine.py:286-299`) and calls
   `direct_ingress.send_outcome` (`direct_ingress.py:322-446`): ONE HTTP POST of all actions to the
   n8n `chatbot-sender` webhook on the default workspace (`chatbot_sender_url`).
3. n8n's `chatbot-sender` (`documentation/n8n/chatbot-sender.workflow.json`) runs the five action
   kinds (`app/services/chatbot/contracts.py:445-451`) in order: `send_message` (sendmsg sub),
   `send_attachments` (send-attachments sub), `assign_conversation`, `add_comment` (mentions as
   `{{@user.<id>}}`), `update_contact_fields`.
4. Outcome rules today: `refused` is re-sent up to 3 times (`inbox_queue.py:73`, `:709-715`);
   `timeout` / `http_error` flags the row `failed` at stage `send_unconfirmed` for staff
   (`:677-706`); a dead process's row is recovered from the logged outcome (`:1048-1087`).
5. Without a sender URL + key, `sender_configured` (`direct_ingress.py:215-227`) is False and the
   covered contact silently stays on the n8n producer path (`skip_reason` "no_sender", `:191`).
6. Operator Retry on the turn trace (`app/api/v1/system/chatbot.py:520-620`) re-posts the original
   respond.io body to n8n's inject webhook (`app/services/chatbot/dispatch.py:416-479`).

## 2. What this lane changes

One new switch, **"Bot replies sent by"**: `n8n` (default, today's behaviour byte for byte) or
`CRM`. Read per send, so flipping it takes effect on the next reply, no deploy, no restart.

With the switch on CRM:

1. `send_outcome` executes the actions itself instead of POSTing to n8n, through the existing
   `RespondClient` (`app/services/integration_service.py`): `send_message` (`:465`, through the one
   outbound gate `_post_contact_message`, `:377`, so the per-contact outbound switch still applies),
   `send_attachment` (`:470`), `set_conversation_assignee` (`:639`), `create_comment` (`:528`),
   `update_contact` (`:794`). Quick replies, attachments and the failure reply follow the n8n subs'
   behaviour (section 4; facts from the research pass and the behaviour card).
2. Each action is one outbound `integration_log` row (LESSONS: every respond.io send logs success
   AND failure), under the existing channel `chatbot_sender`, so the trace screen and recovery
   (`_last_send_outcome`, `inbox_queue.py:1027`) keep reading the same rows.
3. Progress is per action: a retry resumes at the first action not confirmed sent, so an already
   delivered first part is never sent twice.
4. Failure classes (owner 11 Nov):
   - refused (respond.io answered 4xx other than 408/429, or the connection was refused, or the
     contact's outbound switch is off): nothing left; retryable. The drain retries 429/connect
     errors with backoff, as today's 3 attempts.
   - unknown (timeout, 5xx after the request left): the sender looks the message up
     (`RespondClient.list_messages`, `:556`) for an outgoing message with the same text after the
     attempt's stamp. Found = confirmed sent; not found = treated as refused and retried; the lookup
     itself failing = the row is flagged for staff with the plain reason and Try again.
   - confirmed (2xx): locked, never resent.
5. `sender_configured` counts the CRM sender as configured when the switch is on (the n8n URL is
   then not needed), so a covered contact no longer depends on n8n.
6. Operator Try again on a failed or unconfirmed turn: with the switch on, it re-sends that turn's
   unconfirmed actions through the CRM sender (resume rule above), instead of re-posting to n8n.
   With the switch on n8n, Retry stays exactly as today.

With the switch on n8n nothing changes: same POST, same body, same headers, same log rows.

Rollback: switch back to n8n. The next send POSTs to n8n again.

## 3. Out of scope (later lanes)

Missed-message poller (B), bot pause and comments mirror (C), SLA schedule / close (D), revise (E),
attachment extraction (F), removing n8n code and settings (G). Direct ingress mode is not changed
by this lane; the owner sets it.

## 4. Open facts (from the n8n subs; not in the repo)

Filled from the research pass and the behaviour card answers before tests are written: quick reply
format on WhatsApp, 24 h window behaviour, attachment link fallback, the failure reply wording,
whether the sendmsg sub writes anything back to the CRM after a send.

## 4b. Contract: `app/services/chatbot/crm_sender.py` (new)

- `split_text(text: str, *, with_quick_replies: bool) -> list[str]`: the n8n sendmsg chunk rule
  (`PLAN-quoted-reply-07oct.md:153-158`). Limit `TEXT_PART_MAX_CHARS = 3900`, or
  `QUICK_REPLY_PART_MAX_CHARS = 1024` when quick replies ride the message. Cut at paragraph
  breaks (`\n\n`) first, then line breaks; a single line longer than the limit is cut at the limit.
  Parts are stripped of surrounding blank lines; an empty / whitespace text gives `[]`. Joining the
  parts back loses no non-whitespace character.
- `send(session_factory, *, turn_id, contact_id, actions, ctx=None, client=None) -> str` returns a
  `direct_ingress.SEND_*` value and never raises. `client` defaults to
  `RespondClient.for_identifier(db, contact_id)`; tests pass a fake.
- Steps, in action order: `send_message` -> one step per text part (quick replies, comma-joined
  input split and trimmed, on the LAST part only, as `RespondClient.send_quick_reply(identifier,
  text, replies)`: a NEW method that builds `{"message": {"type": "quick_reply", "title": text,
  "replies": replies}}` and goes through `_post_contact_message`; payload UNVERIFIED, Q4);
  `send_attachments` -> one step per `attachments_src` entry, `send_attachment(identifier, type,
  url, caption)` with type `image` / `video` / `audio` from `attachmentType` or `mimeType`, else
  `file`; `assign_conversation` -> `set_conversation_assignee(identifier, respond_user_id)`;
  `add_comment` -> `create_comment(identifier, "{{@user.<id>}} ..." + "\n" + text)` (no mention
  line when there are none, exactly the n8n expression); `update_contact_fields` ->
  `update_contact(identifier, {"custom_fields": [{"name": k, "value": v}, ...]})`
  (`app/tasks/respond_io_tasks.py:936-939`). Unknown kinds and `dry_run` actions are skipped (the
  n8n sender's `explode-actions` drops dry runs). The identifier is `id:<contact_id>`.
- Step key `"<action index>.<part index>"`. Each attempted step writes ONE `integration_log` row:
  channel `chatbot_sender`, `business_table = chatbot.turns`, `business_id = turn_id`, direction
  outbound, `request_payload` JSON carrying `{"sender": "crm", "step": key, "kind": ..., ...}`,
  status `success` / `failed`, `status_code`, plain `error_message`.
- Resume: before sending, the steps whose latest row for this turn is `success` are skipped.
- Outcome per step: 2xx = confirmed. Refused = `httpx.ConnectError` / `ConnectTimeout`, an
  `HTTPStatusError` with status 4xx other than 408, or an `AppException` from the outbound gate
  (`OUTBOUND_DISABLED`, `respond_outbound_service.py:127`): stop, return `SEND_REFUSED` (nothing
  of that step left). Unknown = read timeout, 408, 5xx: Q2. The first non-confirmed step stops the
  run; later steps are not attempted.
- Recovery (`inbox_queue._last_send_outcome`, `:1027`) must not read a confirmed FIRST step as the
  whole reply sent: on the CRM path a row is done only when every step is confirmed.

## 4c. Contract, round 2 (from the answers)

- Columns on `system_settings` (migration, additive): `chatbot_reply_sender_mode` String(16) NOT
  NULL server_default `n8n`, values `n8n` / `contacts` / `all`; `chatbot_reply_sender_contacts`
  Text NULL (same format as `chatbot_direct_ingress_contacts`, parsed by
  `direct_ingress.listed_contacts`). Both in the settings GET dict builder
  (`app/api/v1/user_management/settings.py:546`), the PUT schema (`:220`) and the defaults
  (`:1191`). Edited by whoever can edit the chatbot settings today (same route guard).
- `crm_sender.covers(row, contact_id) -> bool` (mode `all`, or `contacts` and listed).
- `direct_ingress.send_outcome`: if the turn already has a `sender: crm` log row, or
  `crm_sender.covers(settings, contact_id)`, it calls `crm_sender.send(...)` and returns its value;
  otherwise the n8n POST, unchanged. So a turn mid-send stays on the path it started on.
- `direct_ingress.sender_configured(db, contact_id=None)`: True when the CRM sender covers the
  contact (mode `all` when no contact is given), else today's URL + key check.
- Unknown outcome (read timeout, 408, 5xx) on a message step (text, quick reply, attachment):
  `client.list_messages(identifier, limit=20)`; an OUTGOING message created at or after the step's
  attempt time (minus 5 s) whose text equals the part (attachment: whose url equals the file url)
  = confirmed (log row `success`, `facts`/payload `"confirmed_by": "lookup"`), the run goes on. Not
  found = return `SEND_REFUSED` (the drain resends from that step). Lookup raises = return
  `SEND_TIMEOUT` (the drain flags `send_unconfirmed`, "Not confirmed").
  Assign and contact-field steps are idempotent: unknown = resend once in the run, then refused.
  A comment has no read-back (`integration_service.py:528-541`): unknown = `SEND_TIMEOUT`.
- Recovery on the CRM path (`inbox_queue._recover_dead_rows`, `:1048`): a row whose every step is
  confirmed is done; otherwise it is flagged `send_unconfirmed` (never re-run the turn: a new answer
  could differ). Try again finishes it.
- Try again (`POST` retry route, `app/api/v1/system/chatbot.py:520-620`), on a turn that has a
  `sender: crm` log row or is covered by the switch: re-send that turn's stored actions
  (`row.response["actions"]`, split with `engine.split_send_actions`) through `crm_sender.send`,
  which skips confirmed steps; the outcome sets the row `done` (all confirmed) or keeps it failed
  with the plain reason; answers 200 / 502 with a plain message. `retry_available` is True for such
  a turn even with no n8n inject URL. A turn on the n8n path keeps today's Retry.
- Message id link: each confirmed message step writes the returned `messageId` in its log row's
  `response_payload`, sets Redis `chatbot:sent-msg:<messageId>` = turn id (TTL 24 h), and runs
  `UPDATE chat_histories SET chatbot_turn_id = :turn WHERE contact_id = :c AND message_id = :m AND
  chatbot_turn_id IS NULL` (the webhook row may already be there). The webhook, on an outgoing row
  with no turn id, reads the Redis key and passes it as `chatbot_turn_id`. Redis down = no link
  (the trace still has the log rows), never a failed send.
- Settings > Chatbot: a select "Bot replies sent by" with options `n8n`, `CRM for listed contacts`,
  `CRM for all`, and a contacts textarea shown only for the listed option, built exactly like the
  Direct ingress pair on the same page (`page.tsx:264-290`).

## 5. Build slices (one lane, one PR)

1. Migration: one column on `system_settings` (the switch), added to the manual dict builder in
   `app/api/v1/user_management/settings.py` (`:546`) and its schema (`:220`).
2. `app/services/chatbot/crm_sender.py`: the action executor and the outcome rules above.
3. `direct_ingress.send_outcome` / `sender_configured` read the switch.
4. Retry route branch for the CRM sender.
5. Settings > Chatbot: the switch beside Direct ingress (existing select; no mock: it reuses the
   page's own select, `sorento_crm_frontend/app/(protected)/user-management/settings/chatbot/page.tsx:264`).
6. User guide: the chatbot settings page under `documentation/user-guides/`.

## 6. Tests (tester writes first, from the UAC)

All with a fake `RespondClient` (no network): switch default n8n; n8n path unchanged (body,
headers, log row); CRM path sends each kind in order; long reply parts in order; quick replies;
attachments; refused retried; timeout + lookup finds it = no resend; timeout + not found = resend;
lookup fails = flagged with reason; resume skips confirmed parts; outbound switch off = refused, no
POST; `sender_configured` True with CRM switch and no URL; Retry route resends via CRM; settings GET
and PUT carry the switch; FE select saves and shows the value.

## 7. Standing rules that apply

Admin switch OFF by default, screen unchanged with it off; every external call logged; every failed
write retryable (refusal releases, only confirmed success locks, unknown outcome checked before
retry, plain reason + Try again); nothing hangs; plain business words on the switch; no internal ids
on screen; chatbot reply format unchanged (the CRM sends what the engine composed).
