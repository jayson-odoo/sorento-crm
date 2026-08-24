# PLAN - Monitoring / Observability Enhancement

**Status:** PLANNED (2026-07-20) - UAC written, decisions locked in grill. No code written.
Next action: kick off the **S4 n8n contract change** (external dependency, longest lead time) in
parallel with starting **S2**.
**Slug:** `monitoring-enhancement`
**UAC (contract, written first):** `documentation/plans/observability/monitoring-enhancement-acceptance-criteria.md`
**Test report (Phase-2 output):** `documentation/plans/observability/monitoring-enhancement-test-report.md`

## Classification - CORE

**CORE.** Observability is a core system function, not a reusable capability a tenant installs.
Per `PRINCIPLES.md` §Modular architecture:

- No `app_modules_catalog` entry, no `tenant_modules` row, **no `require_module_enabled_with_api_key`
  guard** on these routes. New endpoints mount under the existing `system` router group in
  `app/api/v1/__init__.py`, which already carries the `system` module key.
- **`public` schema, normal FKs.** New tables (`api_call_log`) and new columns (`chat_histories.*`)
  live in `public`. Nothing here passes the uninstall test - you cannot turn off "knowing whether
  the system works".

## Goal

Six slices that convert "the system tells us it is broken when it is fine, and stays silent when it
is broken" into trustworthy signal:

| Slice | One line | Ship order |
|-------|----------|-----------|
| **S2** | Scheduled-task overdue is computed from scheduler truth, with grace, and the alert email is actionable | **1st** |
| **S4** | WhatsApp round-trip latency measured on Respond's clock, p99 ≤ 10s, alerted | 2nd (n8n side starts immediately, in parallel with S2) |
| **S5** | Chat history admin UI + streamed CSV export + `user_downloads` purge | 3rd |
| **S1** | Health dashboard: date range, four-bucket classification, benign reclassification | 4th |
| **S3** | `api_call_log` - total external/MCP request telemetry by construction | 5th |
| **S6** | Timezone rendering standard + ESLint burn-down | 6th |

**Why S2 first.** It is the cheapest slice *and* it is actively harmful today: it emits false
"overdue" alert email. S4/S1/S3 all add alerting. Alerting added on top of a channel the user has
already learned to ignore is worth nothing. Restore trust in the alert channel, then load it.

**Why the S4 n8n work starts on day one.** It is the only external dependency in the whole feature
(three node changes across two subworkflows on a live production automation). Its lead time is
wall-clock, not effort, so it must not sit behind S2's code.

## Phase discipline

Per `CLAUDE.md` / `PRINCIPLES.md`, each slice runs Phase 1 (FE prototype on mocks) → Phase 2 (BE
wiring, **test-first red→green→refactor**) → Phase 3 (code review). Slices with no meaningful new UI
**skip Phase 1** and say so:

| Slice | Phase 1 (FE mock prototype) | Notes |
|-------|------------------------------|-------|
| S2 | **Minimal** - one new form field only | Prototype the grace field + the alert-email HTML preview; no new page |
| S4 | **SKIPPED - backend-only** | No user-facing UI in S4. Its metrics surface in S1's dashboard and S5's grid, which have their own Phase 1. Alert email body is prototyped as a rendered fixture, not a screen. |
| S5 | **Required** - full grid + drawer + export | The largest FE surface in the feature |
| S1 | **Required** - date picker, four-bucket cards, drill-through | Reworks an existing page |
| S3 | **Required (small)** - one new list page | Middleware itself is backend-only |
| S6 | **N/A** - no new UI; it is a defect fix + a lint rule | Verified by rendered output, not by prototype |

---

# S2 - Scheduled-task overdue correctness (SHIPS FIRST)

**UAC ids:** OBS-S2-01 … OBS-S2-14.

## The three bugs

1. **`next_run_at` is display-only but is what "overdue" reads.**
   `app/services/scheduled_task_service.py:63` - `compute_next_run` is documented verbatim as
   *"Display-only next-run estimate. Due-check is frequency-based at query time."* The real
   scheduling decision is `_is_task_due(task, now)` at `app/services/scheduled_task_service.py:82`,
   which uses `now - last_run_at >= interval`. Both overdue readers query `next_run_at` instead.
   They are reading a field the scheduler does not obey.

2. **The two readers disagree with each other, by design, in code comments.**
 - `app/api/v1/system/health.py:148` counts `enabled AND (next_run_at IS NULL OR next_run_at < now)`.
 - `app/services/system_health_alert_service.py:110` counts `enabled AND next_run_at IS NOT NULL
     AND next_run_at < now`, with a comment explaining that NULL is excluded to dodge a transient
     false alert during the just-seeded window.
   So the dashboard and the alert can never agree, and the alert's NULL exclusion is a
   workaround for a symptom of bug 1.

3. **Zero grace.** `next_run_at < now` fires the instant a run is one second late. The scheduler
   heartbeat has finite resolution, so healthy tasks are permanently "overdue".

4. **The alert email is not actionable.** `_eval_scheduled_tasks` returns
   `"overdue: " + ", ".join(keys)` - task keys only. No lateness, no interval, no link.

## Design

**One shared helper. Both callers use it. The divergent inline queries are deleted, not patched.**

New in `app/services/scheduled_task_service.py` (co-located with `_is_task_due`, which is the truth
it mirrors):

- `compute_due_at(task) -> datetime | None` - `last_run_at + interval`; when `last_run_at` is NULL,
  `start_at or created_at`; returns `None` when `start_at` is in the future (not yet eligible).
- `effective_grace(task, global_percent) -> timedelta` - `clamp(percent × interval, 60s, 30min)`.
- `overdue_tasks(db, now) -> list[OverdueTask]` - the single entry point returning a small dataclass
  carrying `task, due_at, lateness, grace` so the alert email can itemize without re-deriving.

Grace percent resolution order: `task.metadata_["grace_percent"]` → `system_settings` global
(default **25**). `ScheduledTask.metadata_` is the existing JSONB column at
`app/models/scheduled_task.py:27` (`Column("metadata", JSONB)`), so **no migration is needed for
per-task grace** - only for the global `system_settings` column.

Call sites replaced:
- `app/api/v1/system/health.py:148` → `len(overdue_tasks(db, now))`.
- `app/services/system_health_alert_service.py:110` → `overdue_tasks(db, now)`, feeding the itemized
  email.

**Alert email.** Itemize per task: key, `name`, human interval ("every 15 minutes"), `last_run_at`
in Malaysia wall-clock, lateness from `due_at` ("23m late"), and a deep link to
`/system-management/scheduled-tasks/{id}`. De-dup, cooldown, and the recovery notice ride the
existing `health_alert_state` machinery at `app/services/system_health_alert_service.py:52` - 
unchanged.

**Lateness is measured from `due_at`, not `due_at + grace`.** Grace decides *whether* to alert;
lateness reports *how late the run actually is*. Reporting from the grace boundary would understate
by up to 30 minutes.

## Impact checklist

- **Migration:** one `system_settings` column (`scheduled_task_grace_percent`, default 25). Per-task
  override needs none (existing JSONB).
- **RBAC / module guard:** none - existing `system` routes.
- **list_query registry:** none.
- **Embedding pipeline:** none.
- **Worker / RQ:** none. No `app/tasks/*` edit, so **no worker restart needed** for this slice.
- **DoD gate #4 (new column reaches FE):** `scheduled_task_grace_percent` must be added to the
  `system_settings` GET dict builder **and** the `*Update` schema in
  `app/api/v1/user_management/settings.py` - schema inheritance alone drops it (see
  `app/api/v1/user_management/settings.py:143` for the pattern).

## Phases

**Phase 1 (minimal FE).** Add the "Grace period (%)" field to the scheduled-task edit form against a
mocked task object; show effective value with the global as placeholder, empty = use global. Render
the new alert-email body as a static HTML fixture for the user to approve the wording before the
watchdog emits it. Verify in browser via sidebar click (System Management → Scheduled Tasks → task).
No backend code.

**Phase 2 (test-first).**
Red first, in this order:
1. pytest for `compute_due_at`: last_run + interval; NULL last_run; future `start_at`
   (OBS-S2-01/02/03).
2. pytest for `effective_grace` clamp boundaries at 60s and 30min, and the exact
   `now == due_at + grace` / `+1s` boundary (OBS-S2-04).
3. pytest for per-task override beating the global (OBS-S2-05).
4. **The convergence test** (OBS-S2-06): seed a fixture set spanning every edge (NULL `last_run_at`,
   future `start_at`, disabled, just-ran, long-overdue), assert the health endpoint's overdue set and
   the watchdog's overdue set are the *same set of keys*. This test is the one that must fail before
   the refactor and pass after.
5. pytest for the itemized email body (OBS-S2-08/09) and de-dup/recovery (OBS-S2-10).
Then implement, then delete the two inline queries.
vitest: grace-field validation + placeholder behaviour (OBS-S2-12/14).
Playwright: sidebar → task → set grace 50 → save → reload → assert persisted + correct PUT
(OBS-S2-13).
Then run the watchdog against the local prod-copy DB and confirm zero overdue while healthy
(OBS-S2-11).

**Phase 3.** `/code-review`. Reviewer specifically checks that `next_run_at` no longer appears in any
overdue code path.

---

# S4 - WhatsApp round-trip latency SLA

**UAC ids:** OBS-S4-01 … OBS-S4-23. **Backend-only - Phase 1 SKIPPED.**

## What is being measured

t0 → t1 where **t0 = the incoming WhatsApp message's Respond timestamp** and **t1 = the outgoing
reply's Respond-side `sent` timestamp**. Both are on **Respond's clock**, so the measurement carries
**zero clock skew**. The CRM's own clock is captured separately as `ingest_at` purely to diagnose
webhook lag; it is never part of the SLA number.

## Evidence - why turn_id is non-negotiable

A proxy measurement over **634 pairs** joined by a 5-minute time window gave:

| percentile | value |
|-----------:|------:|
| p50 | **5.00 s** |
| p95 | 181.74 s |
| p99 | 265.04 s |

The tail is an **artifact of temporal mispairing**, not real latency: the maximum observed is 295 s,
which saturates the 5-minute join window - a distribution truncating exactly at the window boundary
is the signature of the window doing the pairing, not the system. **p50 = 5 s is the trustworthy
part of this data; p95/p99 are not.** This is precisely why pairing moves to an explicit `turn_id`
rather than a heuristic time join, and why the target is set against p50-grounded reality
(**p99 ≤ 10 s**, i.e. 2× the trustworthy median) rather than against the artifact.

## n8n contract (EXTERNAL DEPENDENCY - start immediately)

Production workflow: `https://automate-sorento.foundryx.my/workflow/9qVyfUxmRQqrpGRMDLRuz`
- save-incoming subworkflow: **`UrETd-jm46tFj3Xw7w8vL`**
- send subworkflow: **`aoydkG1dbItXR5jXFEQsP`**

Three changes, both directions:

| # | Node | Change | Why |
|---|------|--------|-----|
| 1 | save-incoming | `sent_at` = raw Respond `message.timestamp` (epoch ms), **not** `new Date().getTime()` | Today `sent_at` is n8n's clock, so t0 already carries skew before anything else happens |
| 2 | save-incoming **and** send | populate `message_id` | Baseline: **4 of 1519 rows** - effectively never. Without it the resolver has nothing to look up |
| 3 | save-incoming **and** send | `turn_id` = `{{ $execution.id }}` | Explicit pairing key; also deep-links to the n8n execution for triage |

**Deploy-ordering safety (OBS-S4-04).** `app/api/v1/external/chat_history.py` gains **OPTIONAL
fields only** and its Pydantic model keeps `extra=ignore`. So: old n8n payload + new CRM = validates
and inserts (fields NULL). New n8n payload + old CRM = extra keys ignored. **Either side can deploy
first without an outage.** This is deliberate - a live WhatsApp pipeline cannot take a coordinated
cutover.

## Resolution - a scheduled task, not polling, not per-row RQ jobs

**No polling.** t1 is fetched by a targeted `GET /v2/message/{id}`
(https://developers.respond.io/docs/api/8fcf4206c2503-get-a-message). The client method already
exists: `RespondClient.get_message` at `app/services/integration_service.py:335`.

> **Signature gotcha.** It is `get_message(self, identifier, message_id)` and builds
> `/v2/contact/{identifier}/message/{message_id}` - it needs the **contact** too, not just the
> message id. Pass `identifier = f"id:{row.contact_id}"`, since `chat_histories.contact_id` is the
> Respond.io contact id string.

New scheduled task **`chat_delivery_resolver`**, every 60s:

```
SELECT ... FROM chat_histories
WHERE message_id IS NOT NULL AND respond_ts IS NULL AND resolve_attempts < 5
ORDER BY sent_at ASC LIMIT 200
```
Per row: call `get_message`; on success write `respond_ts` (+ `delivery_status`, and `delivered_ts` /
`read_ts` when present); on **404 increment `resolve_attempts`**; at 5 attempts set
`delivery_status = 'not_sent'` and stop selecting it. **Message not found means NOT SENT** - never
"assume sent". Transport errors / 5xx do not abort the batch (OBS-S4-10).

**Why a scheduled task rather than per-row RQ jobs:** the enricher then appears in the
scheduled-tasks run-log UI and is itself observable (OBS-S4-11). An observability feature whose own
data pipeline is invisible would be self-defeating. Register the handler alongside the others in
`app/scheduler/task_scheduler.py` (see the `register_handler(...)` block at lines 279 - 296) and seed
the row via an Alembic migration.

## SLA definition

- **Pairing:** by `turn_id` only. Rows with `turn_id IS NULL` (proactive/broadcast sends) are
  **EXCLUDED from the denominator**, never guessed at (OBS-S4-13). The ~1519 pre-existing rows all
  fall in this bucket, which is the correct outcome - not a backfill gap (OBS-S4-23).
- **The clock STOPS at `sent`** (Respond accepted). `delivered` / `read` are captured and displayed
  but **not** SLA'd: a recipient with their phone off must not blow p99. Undeliverability is tracked
  as its own metric - `undelivered_over_15m` (OBS-S4-14/15).
- **Target p99 ≤ 10s**, stored in `system_settings`, user-editable (OBS-S4-16).

## Alerting - ON from day one

High-volume, business-critical, so no soak period. All three ride the existing `health_alert_state`
de-dup with cooldown + recovery notice (`app/services/system_health_alert_service.py:52`):

| Key | Trigger |
|-----|---------|
| `whatsapp_latency_degraded` | rolling p99 over the **last 200 turns**, recomputed every 60s, exceeds target |
| `whatsapp_stalled_turn` | a single turn exceeds **3× target (30 s)** |
| `whatsapp_no_reply` | an incoming message with no outgoing row for its `turn_id` after **5 min** |

A minimum sample floor guards the p99 alert (OBS-S4-20) - no alerting off three turns. Every alert
deep-links the n8n execution via `turn_id`.

## Migration

`chat_histories` (high volume - additive only, all nullable/defaulted, no table rewrite):
`respond_ts`, `delivery_status`, `delivered_ts`, `read_ts`, `resolve_attempts` (default 0),
`turn_id`, `ingest_at`. Plus a partial index for the resolver sweep
(`WHERE message_id IS NOT NULL AND respond_ts IS NULL`) and one on `turn_id` for pairing. Existing
indexes are at `app/models/chat_history.py` `__table_args__` - follow their partial-index style.

## Impact checklist

- **Migration:** yes (above) + `system_settings` p99 target. New `down_revision` must chain onto a
  **committed** main head; `alembic heads` reads the filesystem and will lie about uncommitted WIP
  migrations.
- **RBAC / module guard:** none new. Ingest stays on `X-API-Key`.
- **list_query registry:** none in S4 (S5 registers `chat_histories`).
- **Embedding pipeline:** none - latency numerics are answered by SQL, never embedded, consistent
  with the stock/order-numerics rule.
- **Worker / RQ:** the resolver is a **scheduler** handler, not an `app/tasks/*` RQ task, so no
  worker restart. If the alert email is enqueued through the email outbox, that path is unchanged.

## Phases

**Phase 1 - SKIPPED (backend-only).** Recorded here explicitly per methodology. The alert-email body
is prototyped as a rendered fixture for wording approval; that is not a UI prototype.

**Phase 2 (test-first).** Red first:
1. pytest: ingest accepts a legacy payload with none of the new fields (OBS-S4-04) - write this
   before touching the schema.
2. pytest: `ingest_at` on CRM clock vs `sent_at` on Respond clock (OBS-S4-05).
3. pytest: resolver selection query, batch cap, ordering (OBS-S4-07); success write (OBS-S4-08);
   404 → attempts → `not_sent` at 5 (OBS-S4-09); 5xx does not abort batch (OBS-S4-10). Respond HTTP
   is stubbed at the `RespondClient` boundary.
4. pytest: latency = outgoing `respond_ts` − incoming `sent_at` for a shared `turn_id`
   (OBS-S4-12); NULL `turn_id` excluded from the denominator (OBS-S4-13); clock stops at `sent`
   even when `delivered_ts` is much later (OBS-S4-14); `undelivered_over_15m` (OBS-S4-15).
5. pytest: each of the three alert conditions, plus the sample floor and de-dup/recovery
   (OBS-S4-17…21).
Then implement. Playwright: scheduled-tasks page via sidebar shows `chat_delivery_resolver` with a
run log (OBS-S4-11). Then verify against live n8n traffic and record the **real** p50/p95/p99 over
turn_id-paired turns in the test report - that number supersedes the 634-pair proxy above.

**Phase 3.** `/code-review`. Reviewer checks: no time-window pairing survives anywhere; not-found is
never treated as sent; `delivered`/`read` are absent from the SLA computation.

---

# S5 - Chat history admin UI + export + downloads purge

**UAC ids:** OBS-S5-01 … OBS-S5-15.

## Registry + list

Register `chat_histories` in `app/services/list_query_registry.py` `ADAPTERS` (the dict at line ~67)
with a `resource_key`, `view_slug`, `export_slug`, model, `compile_prefix`, `display_name`, and a
serializer - following the `tickets` entry as the closest precedent. Registration is what buys
filters, column preferences (`listing_key` → `GET|PUT|DELETE /api/v1/list-query/column-config/...`),
and the export permission slug.

**Grid:** one row per message. Columns - time (Malaysia), contact (**resolved name + phone**),
direction, message (truncate + `title`), latency (outgoing rows only), delivery status.
`tableLayout: { width: 'fixed', columnsResizable: true }`, `columnResizeMode: 'onChange'`, explicit
`size` per column. Filters: date range on `sent_at` (default **last 24h**), contact, direction,
**breached only**. Params via `buildDataGridParams` - never hand-built.

> **Documented gotcha (OBS-S5-04).** `chat_histories.contact_id` is the **Respond.io id STRING**, not
> `respond_contacts.id`. Name resolution requires a join on the Respond-id column, with a phone-number
> fallback when no contact row matches. Rendering the raw id would also violate the no-UUIDs/no-opaque-
> ids-in-UI rule.

**Row click → side drawer** with that contact's threaded transcript centred on the selected message.
This same drawer is the per-contact conversation view - one component, not two.

**Pagination: keyset on `(sent_at, id)`.** The composite indexes already exist on `chat_histories`
(`ix_chat_histories_channel_contact_sent_id`, `ix_chat_histories_channel_phone_sent`,
`ix_chat_histories_channel_type_sent`). Offset paging on a table this size degrades and can skip or
repeat rows under concurrent inserts.

## Export - a new My Downloads producer

Kind `chat_history_export`. Server-side CSV **streamed from a DB cursor** - constant memory, no row
ceiling - uploaded via `storage_router` to `exports/chat-history/{download_id}/{filename}.csv`.

Follow the producer contract established by `generate_complaint_pdf` at `app/tasks/export_tasks.py:18`
exactly: `mark_processing` → produce → `upload_file` → `mark_ready`, and on **any** exception
`mark_failed` and **return** - **never raise into RQ's failed registry**. Add a `KIND_LABEL` entry in
`sorento_crm_frontend/components/my-downloads/DownloadRow.tsx:21` (today it contains only
`complaint_pdf`), or the drawer renders the raw kind string.

## `user_downloads` purge - closing a real existing gap

New scheduled task `user_downloads_purge`. **Today nothing purges `user_downloads` at all** - 
`complaint_pdf` files accumulate in storage forever. The purge applies to **all kinds**: delete the
storage object then the row past retention (default **30d**, configurable). A missing storage object
must not abort the sweep (already-deleted objects are normal).

## Permissions

New slugs for chat-history **view** and **export**, granted to `superadmin` / `admin` initially.
**Message content is PII - it is gated.** Per DoD gate #3 the migration must run a **grant sweep over
already-provisioned roles**, not seed-if-absent, or the page silently 403s and the sidebar entry
hides.

## Impact checklist

- **Migration:** permission slugs + grant sweep; `system_settings` download-retention days. No new
  table.
- **RBAC / module guard:** new slugs (above). Routes mount under the existing guard set.
- **list_query registry:** **yes** - a new `ADAPTERS` entry (OBS-S5-01).
- **Embedding pipeline:** none. Chat content is already handled by the existing RAG path; this slice
  adds no new embedding source.
- **Worker / RQ:** **yes** - new RQ task in `app/tasks/export_tasks.py`. **The worker has no reload - 
  restart it after editing `app/tasks/*`.** Local worker needs
  `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` on macOS or RQ's forked work-horse aborts with signal 6.

## Phases

**Phase 1 (required - largest FE surface).** Build the grid, filters, drawer, export button, and My
Downloads row against `__mocks__` fixtures covering: loading, empty, error, a resolved-contact row, an
unresolved-contact row falling back to phone, a breached-latency row, and a `not_sent` row. Verify by
clicking through the sidebar. Screenshot golden path + every state. Document the request/response
contract at the top of the feature service. No backend code, no tests yet.

**Phase 2 (test-first).** Red first: registry adapter resolution and permission slugs (OBS-S5-01/13);
keyset pagination stability across a concurrent insert (OBS-S5-06); contact-name join incl. the
no-match fallback (OBS-S5-04); export task marks failed and does not raise (OBS-S5-10); purge deletes
object + row and survives a missing object (OBS-S5-12). Then implement; then swap FE mocks for real
hooks and delete the fixtures not reused by tests. vitest for grid/drawer states. Playwright:
sidebar → filter → drawer → export → download, zero console errors (OBS-S5-14). Verify at 375px and
1280px (OBS-S5-15).

**Phase 3.** `/code-review`. Reviewer checks: no raw Respond ids rendered; no hand-rolled
`extractApiError` / `URLSearchParams`; export task cannot raise; every section has an empty state.

---

# S1 - Health dashboard

**UAC ids:** OBS-S1-01 … OBS-S1-10.

## Date range

Global picker at the top of `/system-management/health`, default **last 24h**, filtering on the
underlying records' `created_at`. Point-in-time backlogs (Email Queue **Pending**, Scheduled Tasks
**total**) are **not** range-filtered - they render absolute and are explicitly labelled **"as of
now"**. Mixing a backlog and a windowed rate on one page without labelling which is which is how the
current page misleads.

## Four-bucket classification

**Success / Failed / Benign / In-flight.** They must **sum to total** - assert it as a property test
(OBS-S1-03).

The live case that motivates this: `n8n_crm_chat_outbound` currently shows **success 0, failed 0,
total 13**. The `pending` / `processing` / `sent` rows are counted in the total and rendered
**nowhere**. `_integrations_health` (`app/api/v1/system/health.py:173+`) buckets only `success` and
`failed`; everything else vanishes into the gap between the two.

## Benign outcomes - fix the writers, then reclassify history

**Two-part fix, both required.**

1. **Fix the WRITER.** `app/services/sla_service.py:3647` raises
   `handle_validation_error("Conversation is already responded.")`, which is logged as a **failure**.
   It is a **benign idempotency race**, and **all 46 historical failed rows for the `sla_management`
   channel are this one signature**. The codebase already has the right status value - 
   `idempotent_already_active`, used at `app/api/v1/sla/sla_tracking.py:758`. Use it here. Stop
   manufacturing false failures at the source.

2. **Per-channel benign-signature rule table** mapping known-benign error signatures, applied on
   read, so the 46 historical rows reclassify to **Benign** without a data migration. The table is an
   **allowlist of known-benign signatures** - anything unmatched stays in **Failed** (OBS-S1-07).
   Fixing only the writer leaves history screaming; fixing only the read leaves the writer producing
   new false failures. Hence both.

## Email Queue card

Show the already-computed `failed_last_24h` alongside the all-time figure: **"2 in 24h (63
all-time)"**. The value is already returned - `app/api/v1/system/health.py:107` computes it into
`EmailOutboxHealth.failed_last_24h` - but the card renders four **all-time** totals, which is exactly
why 63 read as a live incident.

> Context, not a work item: `respond_io` historical failures are overwhelmingly 401/403 against
> obvious test contacts (`id:123456`, `55555`, `9999`). Noted so a reviewer does not mistake the
> backlog for a live incident.

## Impact checklist

- **Migration:** none required (rule table can ship as code/config; a `system_settings` entry if the
  user wants it editable).
- **RBAC / module guard:** none.
- **list_query registry / embedding / worker:** none.

## Phases

**Phase 1 (required).** Prototype the date picker, the four-bucket channel table, the reworked Email
Queue card, and drill-through links against mocked health payloads - including a channel with only
in-flight rows and a channel with only benign rows. Sidebar-click verification.

**Phase 2 (test-first).** Red first: the sum-to-total property across generated status mixes
(OBS-S1-03); the `n8n_crm_chat_outbound` in-flight case (OBS-S1-04); the writer now emitting
`idempotent_already_active` (OBS-S1-05); the rule table reclassifying the `sla_management` signature
while an unmatched error stays Failed (OBS-S1-06/07). Then implement. vitest for card rendering and
the "as of now" labelling. Playwright: sidebar → dashboard → change range → click a Failed count →
land on the filtered integration-log list (OBS-S1-09).

**Phase 3.** `/code-review`. Reviewer checks the rule table is an allowlist, not a catch-all.

---

# S3 - `api_call_log`

**UAC ids:** OBS-S3-01 … OBS-S3-13.

## New table (public schema, CORE)

`api_call_log`: endpoint, method, source, actor, status_code, outcome, latency_ms, correlation_id,
truncated request payload, truncated response payload (~**8KB** cap each), `created_at`. Indexes on
`(created_at)`, `(source, created_at)`, `(correlation_id)`.

## Written synchronously by middleware

Middleware alongside `LoggingMiddleware` / `IdempotencyMiddleware` (registered in `app/main.py:49`
and `:54`), scoped to every `/api/v1/external/*` route and every MCP-originated call.

**Coverage is total by construction - no per-endpoint code, and new endpoints are logged the day they
are added.** Today only **3 of ~30** external endpoints log anything (chat-history ingest,
conversation-variables, ideation). The unlogged ones, enumerated from `app/api/v1/external/`:
`view_link`, `next_assignee`, `presigned_url`, `rag`, `memory`, `contact_access_types`,
`packing_lists`, `spo_allocations`, `grn`, `promotions`, `forms`, `stock_inquiries`,
`purchase_requests`, `team_members`, `work_calendar`, `respond_contacts`, `portal_tokens`,
`it_support_tickets`, plus `complaint_attachments`, `entity_attachments`, `product_attachments`,
`stock_inquiry_attachments`, and `access_agent` / `conversation_assignee` /
`conversation_sla_tracking`.

**Synchronous, not buffered-async - deliberate.** A crash must not lose the evidence for the incident
being logged; a buffered writer drops exactly the records you need when the process dies. The cost is
per-request latency, which Phase 2 measures and records (OBS-S3-13). The write failing must never
affect the response (OBS-S3-11).

## MCP attribution

`sorento_crm_mcp/sorento_crm_mcp/http_client.py` sends `X-Source: mcp`, `X-Correlation-Id`,
`X-Tool-Name`. It already measures `elapsed_ms` (`http_client.py:122`, and again in the error branch
at ~:98) but only writes it to the log line - joining that to the server-side span via
`correlation_id` turns two half-measurements into one end-to-end trace and separates network time
from server time.

**Today the backend cannot distinguish MCP from n8n at all**: both authenticate with the same shared
`EXTERNAL_API_KEY` and send no distinguishing headers. Absent `X-Source`, `source` falls back to a
defined default and the row is still written (OBS-S3-06).

## `integration_log` is NOT extended

Deliberate. `integration_log` is a **work-queue** record - `retry_count`, `max_retry_allowed`,
`next_retry_at` - with a UUID `business_id` that chat-ingest already **fakes** with
`str(uuid.uuid4())` (`app/api/v1/external/chat_history.py:107`) precisely because chat ingest has no
business row to point at. That fake is the tell: the table is being borrowed for telemetry it was not
shaped for. It keeps its job (retryable business integrations); telemetry gets its own table.

## Retention

`api_call_log_prune` scheduled task: **NULL payloads at 30d**, **DELETE rows at 180d**, both
configurable in `system_settings`. Payloads are the bulk of the bytes and the shortest-lived value;
the metadata row stays useful for trend analysis long after the body does.

## Impact checklist

- **Migration:** new `api_call_log` table + indexes; `system_settings` retention columns; seed the
  prune scheduled task.
- **RBAC / module guard:** new view slug for the FE page + grant sweep (DoD #3).
- **list_query registry:** optional - register `api_call_log` if the page needs column preferences
  and export; recommended for consistency with S5.
- **Embedding pipeline:** none.
- **Worker / RQ:** none (prune is a scheduler handler).
- **Gotcha:** the middleware must not log its own writes or the health endpoint's polling into a
  feedback loop; scope strictly to `/api/v1/external/*` + MCP-sourced calls.

## Phases

**Phase 1 (required, small).** Prototype the new System Management list page with filters (source,
endpoint, outcome, date range, correlation id) against mocked rows, including empty and error states.
Sidebar-click verification.

**Phase 2 (test-first).** Red first: every external route produces exactly one row (OBS-S3-02);
a newly-added route is logged with no per-endpoint code (OBS-S3-03); payload truncation + secret
redaction (OBS-S3-04) - note the existing precedent that masks `x-api-key` at
`app/api/v1/external/chat_history.py` before persisting headers; MCP header attribution (OBS-S3-05);
missing-header fallback (OBS-S3-06); log-write failure does not affect the response (OBS-S3-11);
prune thresholds (OBS-S3-10). Then implement middleware, then the MCP header change with its own
pytest in `sorento_crm_mcp/tests/`. Measure and record the latency delta. Playwright for the page
(OBS-S3-12).

**Phase 3.** `/code-review`. Reviewer checks: no per-endpoint logging calls were added; no secret
reaches the table; `integration_log` untouched.

---

# S6 - Timezone rendering standard

**UAC ids:** OBS-S6-01 … OBS-S6-06.

## Root cause

**DB stays naive UTC. This is a frontend-only bug.** `new Date("2026-07-02 09:05:00")` has no
timezone suffix, so JS parses it as **browser-local** and produces the wrong instant **before any
formatter runs** - the formatter then faithfully formats a wrong `Date`. The correct approach is to
pass the **raw string** to `formatDateTimeInMalaysia` (`sorento_crm_frontend/lib/helpers.ts:432`),
which routes through `toUTCDate` → `parseDateTimeAsUTC` (`lib/helpers.ts:240`) and appends `Z` when
no offset is present.

## Note on the Last Sign In defect - reproduce before editing

Both current render sites already call `formatDateTimeInMalaysia` on what appears to be a raw string:

- `app/(protected)/user-management/users/components/user-list.tsx:478` - `formatDateTimeInMalaysia(v)`
  where `v` comes from `accessorFn: row => row.last_sign_in_at ?? row.lastSignInAt`.
- `app/(protected)/user-management/users/[id]/components/user-profile.tsx:172` - 
  `formatDateTimeInMalaysia(user.lastSignInAt)`, fed from `[id]/layout.tsx:134`.

So the observed **9:05 am (should be 5:05 pm MYT)** is **not** explained by a naive
`format(new Date(...))` at either site. **Phase 2 must start by reproducing and isolating the actual
instant-mangling step** before changing a line that already looks correct. Prime suspects, in order:
(a) the value being a `Date` object by the time it reaches the formatter - `toUTCDate` returns
`Date` inputs **unchanged** (`lib/helpers.ts:268`), so an upstream `new Date(naive)` conversion is
laundered through silently; (b) `new Date("YYYY-MM-DD HH:MM:SSZ")` - the space-separated form with an
appended `Z` at `lib/helpers.ts:249` - behaving inconsistently across engines; (c) the value
originating from the Prisma/NextAuth DB with different serialization from the FastAPI timestamps.

**The AC (OBS-S6-03) is the observed rendered output, not a presumed line edit.** This is the one
item in the feature where the mechanism is stated as a hypothesis rather than a verified fact, and it
is called out as such rather than guessed at. Suspect (a) is also the strongest argument for the lint
rule below: a `Date` constructed anywhere upstream is invisible at the render site.

## ESLint rule + shrinking allowlist

Ban `format*(new Date(...))` and raw `toLocaleString` / `toLocaleDateString` / `toLocaleTimeString`
on API timestamps, with a shrinking allowlist grandfathering existing sites. **Same playbook as the
SearchableSelect standard** - `eslint.config.mjs` already carries a `no-restricted-syntax` block
(lines 49 - 80) and a `dropdownMigrationAllowlist` override, so this is an additive rule + a new
`eslint-timezone-allowlist.mjs`, not new machinery.

**Measured baseline (verified 2026-07-20):** **103** `format*(new Date(` sites and **~36 - 39** raw
`toLocale*` sites across `app/ components/ lib/ hooks/ services/` - ≈139 total. **Allowlist size is
the burn-down metric.** Sweep in batches per module; a new violating site in a non-allowlisted file
is flagged immediately.

Set the new rule's severity to match the existing precedent: the dropdown *import* ban is `error`
with an allowlist; the architecture-guard syntax rules are `warn` because `eslint .` runs without
`--max-warnings`. Recommend **`error` + allowlist** here so the allowlist genuinely gates new
violations rather than adding to a warning pile nobody reads.

## Impact checklist

- **Migration / RBAC / registry / embedding / worker:** none. FE-only.

## Phases

**Phase 1 - N/A.** No new UI; this is a defect fix plus a lint rule.

**Phase 2 (test-first).** vitest pinning both the wrong behaviour (`new Date(naive)` → wrong instant)
and the right one (`formatDateTimeInMalaysia(rawString)` → correct MYT) (OBS-S6-02). Reproduce the
Last Sign In defect with a failing test at the real render path before touching it (OBS-S6-03). Add
the rule + allowlist; assert a new violating file fails lint while an allowlisted one passes
(OBS-S6-04/05). Playwright: sidebar → Administrative Users → assert the rendered time.

**Phase 3.** `/code-review`. Then burn the allowlist down in per-module batches, reporting its size
each time.

---

# Cross-cutting

## Retention summary

| Data | Payload | Row / file |
|------|---------|-----------|
| `api_call_log` | NULL at **30d** | DELETE at **180d** |
| `user_downloads` | - | file + row DELETE at **30d** |

All thresholds live in `system_settings` and are user-editable.

## New scheduled tasks introduced

| Key | Interval | Slice |
|-----|---------|-------|
| `chat_delivery_resolver` | 60s | S4 |
| `user_downloads_purge` | daily | S5 |
| `api_call_log_prune` | daily | S3 |

Each is registered in `app/scheduler/task_scheduler.py` (the `register_handler` block at lines
279 - 296) and seeded by an Alembic migration. Each therefore inherits the S2 overdue+grace treatment
for free - S2 shipping first means these are monitored correctly from their first run.

## Standing gotchas that apply

- **Alembic:** a new `down_revision` must chain onto a **committed** main head, not an uncommitted WIP
  migration on disk - `alembic heads` reads the filesystem and will lie. Revision ids ≤ 32 chars. If a
  branch merge forks two heads, fix with `alembic merge`.
- **Worker has no reload.** S5 edits `app/tasks/export_tasks.py` → restart the worker session.
  `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` is mandatory on macOS.
- **Local DB is a copy of prod data** (`localhost:5432/sorento_ai_automation`) - safe to migrate and
  test against, which is what makes OBS-S2-11 and the S1 46-row reclassification independently
  verifiable. Real prod migration is a separate deploy.
- **Handoff = prod build.** Every time the user is asked to test :3000, kill dev and run
  `npm run build && npm start`. Never hand off a dev server.
- **DoD #4:** every new `system_settings` column (grace percent, p99 target, three retention values)
  must be added to **both** the settings GET dict builder and the `*Update` schema in
  `app/api/v1/user_management/settings.py` - schema inheritance alone drops it.
- **DoD #3:** every new permission slug (S5 chat-history view/export, S3 api-call-log view) needs a
  grant sweep over already-provisioned roles.

## Open items needing the user's decision

1. **S3 severity of the latency cost.** Synchronous logging is locked, but the *acceptable* p95
   latency delta is not specified. Phase 2 measures it (OBS-S3-13); if it lands above what the user
   considers tolerable for external webhooks, that is a decision point, not something to silently
   absorb.
2. **S6 lint severity.** Recommended `error` + allowlist (above); the existing architecture guards are
   `warn`. Confirm before the rule lands, since `error` will block CI for any new violation.
3. **S3 `api_call_log` list_query registration.** Recommended for consistency with S5 (gets column
   prefs + export for free); not explicitly locked in the grill. Flagging rather than assuming.

## Decision log (locked in grill, 2026-07-20 - not to be re-opened)

| Topic | Decision |
|-------|----------|
| Classification | CORE, `public` schema, normal FKs |
| S2 overdue source | `due_at = last_run_at + interval` - scheduler truth. `next_run_at` never consulted |
| S2 divergence | One shared helper for both readers; the two inline queries are **deleted** |
| S2 grace | `clamp(25% × interval, 60s, 30min)`; global in `system_settings`, per-task override in `ScheduledTask.metadata_` |
| S2 alert content | Itemized: key, name, interval, last run, lateness, deep link |
| S4 clocks | Both endpoints on **Respond's** clock; zero skew. `ingest_at` = CRM clock, diagnostics only |
| S4 t1 resolution | Targeted `GET /v2/message/{id}`, **no polling**. Not found = **NOT SENT** |
| S4 resolver shape | Scheduled task (60s, batch 200, 5 attempts) - **not** per-row RQ jobs, so the enricher is itself observable |
| S4 pairing | `turn_id` = n8n `{{ $execution.id }}` on both saves. NULL `turn_id` **excluded** from the denominator, never guessed |
| S4 SLA boundary | Clock **stops at `sent`**. `delivered`/`read` captured + displayed, never SLA'd. Separate `undelivered_over_15m` metric |
| S4 target | **p99 ≤ 10s**, `system_settings`, user-editable. Alerting **on from day one** |
| S4 alerts | rolling-200 p99 degraded · single turn > 3× target · incoming with no reply after 5min - all through existing `health_alert_state` |
| S4 compatibility | Ingest schema gains **OPTIONAL fields only**; either side deploys first safely |
| S5 registry | `chat_histories` registered as a list_query resource |
| S5 UI | DataGrid (one row per message) + row-click side drawer with threaded transcript; drawer doubles as the per-contact view |
| S5 pagination | Keyset on `(sent_at, id)` |
| S5 export | New My Downloads producer, kind `chat_history_export`, cursor-streamed CSV, `mark_failed` never raise |
| S5 purge | New `user_downloads_purge` for **all** kinds - closes a real existing gap |
| S5 permissions | New view + export slugs; content is PII, gated |
| S1 date range | Global picker, default 24h, on `created_at`; backlogs render absolute, labelled "as of now" |
| S1 classification | Four buckets summing to total: Success / Failed / Benign / In-flight |
| S1 benign | Fix the **writer** (`idempotent_already_active`) **and** add a per-channel benign-signature rule table for history |
| S1 email card | Show `failed_last_24h` alongside all-time |
| S3 table | New `api_call_log`; `integration_log` **not** extended |
| S3 write mode | **Synchronous** middleware - a crash must not lose the incident's evidence |
| S3 attribution | MCP sends `X-Source` / `X-Correlation-Id` / `X-Tool-Name`; join client `elapsed_ms` to the server span |
| S3 retention | Payload NULL @30d, row DELETE @180d, configurable |
| S6 scope | Frontend-only; DB stays naive UTC |
| S6 mechanism | Pass the **raw string** to `formatDateTimeInMalaysia`; never `format*(new Date(naive))` |
| S6 enforcement | ESLint rule + shrinking allowlist (SearchableSelect playbook); allowlist size = burn-down metric |
| Sequencing | S2 → (S4 n8n in parallel) → S4 → S5 → S1 → S3 → S6 |
