# PLAN - Ideation status update: pull the shared service's status-event feed, send the template

**Status:** in review on PR #1357, awaiting CI and the owner hand test, 29 Sep 2026. Track: full track (one migration: a new cursor table plus a
partial unique index on `integration_log`). Issue #1355. UAC:
`ideation-status-update-29sep-acceptance-criteria.md` (AC-IS001 onward).

## The ask, in the owner's words

Owner, 29 Sep 01:0x MYT, verbatim: "btw i merged ideation round 2 from shared service, so CRM side
whatever is needed to start can start now".

Owner rulings recorded on the shared-service side (jayson-odoo/foundryx-shared-service#94, PRs
#95 and #96, plan `documentation/plans/ideation/PLAN-ideation-round-2-merge-unmerge.md`, contract
`documentation/ideation/status-events-contract.md`, AC-94-72), quoted on issue #1355:

- a stage-change notification on every stage, as a new WhatsApp template use case "ideation status
  update", to the requester;
- the shared service publishes an event feed, the CRM pulls it and owns the send (templates,
  opt-outs, integration log in one place); precedent sorento #1201 `ideation_draft_reminder` sent
  by `ideation_turn_service` through Respond.io;
- test ideas must never message a real requester.

Appendix A of the shared-service plan (the CRM brief) is quoted verbatim on #1355 and is the
contract this plan fulfils: template use case, poller, idempotency on `event_id`, guards, always
the approved template, logging.

## The feed contract (from #1355, section 7.1 of the shared-service plan)

`GET {ideation_shared_service_url}/ideation/intake/status-events?after=<seq>&limit=<n>&includeTest=<bool>`
on the workspace-key router, `Authorization: Bearer <key>`, the same key and base URL the CRM
already uses for `POST /ideation/intake/create-idea` (`ideation_turn_service._resolve_ideation_config`:
the default Respond workspace row first, `.env` fallback per field).

- At-least-once. `seq` ascends. Rows younger than a 5 s settle window are withheld.
- Test ideas are excluded unless `includeTest=true`.
- Response: `{ "events": [...], "next_after": <last seq or the given after> }`.
- Event (snake_case):

```
{ "event_id": "uuid", "seq": 812, "kind": "status_changed" | "merged" | "unmerged",
  "occurred_at": "2026-09-28T09:10:00Z",
  "idea_id": "...", "idea_number": "IDEA-0031", "idea_title": "Faster quotation",
  "product_id": "...", "status_label": "Discussed", "from_status_label": "New",
  "track_url": "https://<frontend>/public/ideas/<token>",
  "requester_phone": "+60123456789",
  "merged_into": null | { "idea_number": "IDEA-0012", "title": "..." },
  "separated_from": null | { "idea_number": "IDEA-0012", "title": "..." },
  "is_test": false }
```

## Design

### 1. Template use case `ideation_status_update`

Registered exactly like `ideation_draft_reminder`:

- `app/models/respond_template.py`: `"ideation_status_update"` appended to
  `TEMPLATE_DEFAULT_USE_CASES` (a tuple, no migration; `use_case` is `String(32)`, the key is 22).
- `sorento_crm_frontend/services/whatsappTemplateService.ts`: the `UseCase` union and `USE_CASES`
  get the entry ("Ideation - Status Update", status-update group, the same way #1276 added the
  reminder), so the owner sees it on Integration Management > WhatsApp templates and maps an
  approved template. Category Utility is a property of the template the owner submits to WhatsApp,
  not of the use case; the description says so.
- Three new mapping variables so the suggested body maps one-to-one:
  "Update on your idea {{1}}: it is now {{2}}. Track it here: {{3}}"
  - `idea_number` - the idea number, falling back to the idea title;
  - `status_label` - the new status label, or for `merged` "combined with IDEA-0012", or for
    `unmerged` "handled separately again from IDEA-0012, now Discussed" (Appendix A wording);
  - `track_url` - the public track link; also offered as a URL-button link variable, so a template
    with a dynamic URL button gets the token as its suffix (the existing button machinery in
    `send_template_for_use_case`).
  - `message` (existing variable) carries the whole suggested sentence, for a single-slot template.

### 2. Poller

`app/services/ideation_status_update_service.py` (the ideation service layer, next to
`ideation_turn_service`): `poll_ideation_status_events(db)`.

- One tick = one feed page: `after=<cursor>&limit=100&includeTest=true`. `includeTest=true` so a
  test idea's move reaches the CRM and is logged, never sent (the owner's hand test sees a
  log-only row); the send guard, not the feed filter, is what keeps test ideas away from a
  requester.
- Events are sorted by `seq` and handled one at a time. Per event: write its one log row and move
  the cursor to its `seq` in ONE commit, only after the event is handled. A crash mid-batch leaves
  the cursor on the last handled event; the next tick re-reads from there, and the `event_id`
  dedupe absorbs anything re-delivered.
- Feed failure (transport, non-2xx, malformed body): logged at warning, cursor untouched, the next
  tick retries. Nothing is sent.
- Config not ready (no base URL or key): the tick does nothing (dormant, like the embed).
- Scheduler: `_ideation_status_events_tick` in `app/scheduler/task_scheduler.py`, the same shape
  as `_ideation_idle_sweep_tick`, `IntervalTrigger(seconds=60)`, id
  `ideation_status_events_poll`. Runs only in the worker with `ENABLE_SCHEDULER=true`, like every
  other tick; APScheduler's default `max_instances=1` keeps ticks from overlapping.

### Cursor storage: a small table, and why

New table `ideation_status_event_cursors (id UUID PRIMARY KEY, feed_base_url TEXT NOT NULL UNIQUE,
after_seq BIGINT NOT NULL DEFAULT 0, updated_at)` (uuid `id` per the data-model principle,
`tests/test_schema_uuid_id_principle.py`).

- Not the scheduled task's metadata: this job is an APScheduler interval job like the idle sweep,
  so there is no `scheduled_tasks` row to hold it, and adding one would drag in the heartbeat's
  run-log and admin-edit surface for one integer.
- Not a column on `respond_workspaces`: the base URL and key can come from `.env` with no
  workspace row at all (the `_resolve_ideation_config` fallback), and the cursor would have
  nowhere to live.
- Keyed by the feed's base URL (trailing slash stripped): a seq is only meaningful on the feed
  that issued it. If the owner repoints the CRM at another shared-service instance, the new feed
  starts from its own cursor instead of silently skipping every event below a foreign seq.

### 3. Idempotency

One `integration_log` row per event, keyed `business_table = 'ideation_status_events'`,
`business_id = event_id`. Before handling, a row for that `event_id` means seen: skip, no second
row, no send. A partial unique index `uq_integration_log_ideation_status_event` on
`integration_log (business_id) WHERE business_table = 'ideation_status_events'` makes it a
database guarantee rather than a read-then-write hope. An `event_id` that is not a UUID (off
contract) is mapped to a stable `uuid5` so it still dedupes and still gets its log row.

### 4. Guards, in order, before any send

1. already seen `event_id` -> skip silently (no row);
2. `is_test` true -> log `skipped` / `IS_TEST`, never send, never look up the contact;
3. unknown `kind` -> log `skipped` / `UNKNOWN_KIND`;
4. no `requester_phone` -> log `skipped` / `NO_REQUESTER_PHONE`;
5. Respond.io contact resolved by `requester_phone` (`respond_contacts.phone_number`, exact, then
   digits only so `+60 12-345 6789` and `60123456789` match); no row, or a row with no
   `respond_io_id` -> log `skipped` / `UNKNOWN_CONTACT`;
6. contact opted out (`respond_contacts.outbound_enabled` false, the per-contact outbound switch
   the reminder already honours inside `RespondClient`) -> log `skipped` / `OPTED_OUT`, checked
   up front so the row says why instead of a 403;
7. send: `send_text_or_template(use_case="ideation_status_update")`, the same 24h-window-aware
   sender every CRM auto-send uses. Window open -> the session text (idea number, new status,
   track link, greeting only when the contact has a name); window closed or unknown -> the
   approved template. No valid mapping while the window is closed -> `TemplateSendSkipped` ->
   log `skipped` / `NO_TEMPLATE` with the reason; the poller carries on. Changed on 29 Sep 2026
   by the follow-up plan `PLAN-ideation-update-24h-window-29sep.md` (this step was template-only).

### 5. Send failure

A Respond.io error on the send itself -> log `failed` / `SEND_FAILED` with the error, cursor
advances. See open question 2.

### 6. Log rows

Every send and skip: `integration_channel='respond_io'`, `business_table='ideation_status_events'`,
`business_id=<event_id>`, `external_reference=<idea number>`, `direction='outbound'`,
`endpoint='ideation_status_update'` (the use case), `http_method='POST'`, `status` in
`success | skipped | failed` (never `pending`/`processing`, so the integration-log retry sweeper
never re-sends one), `error_code` = the reason code, `request_payload` JSON carrying `event_id`,
`seq`, `kind`, `idea_number`, `use_case`, `template` (the mapped template name, or null),
`parameters` on a send, `response_payload` = Respond.io's reply on a send. A side-write failure
(the log itself) is caught: the cursor is not moved, the tick stops, the next tick retries; no
exception ever escapes the tick.

## Open questions (with recommendations)

1. **First run.** The cursor starts at 0, so the first tick after deploy walks every event the
   feed holds since the shared-service PR went live (28 Sep) and messages each requester.
   **Recommendation: accept it; the feed is one day old, those are real stage changes nobody was
   told about. If the owner does not want them sent, the orchestrator seeds
   `ideation_status_event_cursors` with the feed's current head before enabling the tick (the
   PR close comment gives the SQL).** Asked on the PR.
2. **Respond.io send failure.** **Recommendation: log `failed` and advance (no automatic retry in
   this PR).** Holding the cursor on a failed send would block every later event behind one bad
   contact; a retry budget is a rule the issue does not set. Asked on the PR.
3. **Unknown `kind`.** **Recommendation: log `skipped` / `UNKNOWN_KIND` and advance**, so a new
   kind added on the shared-service side never stalls the feed.
4. **Contact with no Respond.io id.** **Recommendation: treat as unknown contact (skip + log)**;
   the brief says resolve the Respond.io contact, and a row without an id has none.

## Tests (pytest, Postgres, tests first)

`tests/test_ideation_status_update.py`, stubbed feed client (a fake feed over a list of events,
honouring `after`) and the Respond.io HTTP seam (`RespondClient.send_template_message`) stubbed,
with real `respond_channels` / `respond_message_templates` / `respond_template_defaults` rows so
the mapping path is the production one:

- one send per kind (`status_changed`, `merged`, `unmerged`), parameters asserted;
- at-least-once redelivery skipped, no second row;
- cursor persisted only after handling (a failing log write leaves it put);
- `is_test` never sends and logs; opt-out skips; unknown phone skips; missing mapping skips and the
  batch goes on; feed outage leaves the cursor;
- log row fields asserted; the use case is on the tuple; the scheduler registers the tick at 60 s.

`tests/test_migration_ideation_status_events.py`: upgrade/downgrade over the blank schema.
Vitest: the use case and the three variables are listed on the templates screen.

## Out of scope

Retries of a failed send, a UI for the cursor, any change to the reminder, any shared-service
change.
