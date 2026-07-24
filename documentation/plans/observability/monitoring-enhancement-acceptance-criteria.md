# UAC — Monitoring / Observability Enhancement

**Slug:** `monitoring-enhancement`
**Plan:** `documentation/plans/observability/PLAN-monitoring-enhancement.md`
**Test report (Phase 2 output):** `documentation/plans/observability/monitoring-enhancement-test-report.md`
**Classification:** **CORE** — observability is a core system function, not a tenant-installable
capability. `public` schema, normal FKs, no `app_modules_catalog` entry, no module guard.
**Written:** 2026-07-20 (BEFORE the plan, per `PRINCIPLES.md` §Methodology).

> This file is the **contract**. The plan is the design that fulfils it. The Phase-2 test report
> keys every id below to PASS / FAIL / DEFERRED. A slice is not done until its ids pass the
> Definition-of-Done gate in `PRINCIPLES.md`.

## Id scheme

`OBS-<slice>-<NN>`, where slice ∈ `S1 S2 S3 S4 S5 S6`. Tags: `[BE]` backend, `[FE]` frontend,
`[E2E]` Playwright round-trip, `[T]` unit/integration test, `[EXT]` external (n8n) dependency,
`[MIG]` migration/backfill, `[PERM]` permission grant.

## Slice order (ships in this sequence)

`S2` → (`S4` n8n contract kicked off in parallel, immediately) → `S4` CRM side → `S5` → `S1` →
`S3` → `S6`. Rationale: S2 is the cheapest slice and is *actively harmful today* — it emits false
overdue alerts. Every later slice adds alerting, and new alerts are worthless if the user has
already been trained to ignore alert email.

---

## S2 — Scheduled-task "overdue" correctness + actionable alert email

*Ships first. Backend-heavy with a small FE surface (per-task grace field).*

### Shared overdue helper (kills the health-card / watchdog divergence)

| Id | Given / When / Then |
|----|---------------------|
| **OBS-S2-01** `[BE][T]` | **Given** an enabled `ScheduledTask` with `last_run_at = T` and interval `I`, **When** the shared helper computes due-ness, **Then** `due_at == T + I` — derived from the same scheduler truth as `_is_task_due` (`app/services/scheduled_task_service.py:82`), **and** `next_run_at` is NOT consulted anywhere in the overdue path. |
| **OBS-S2-02** `[BE][T]` | **Given** a task that has **never run** (`last_run_at IS NULL`) and whose `start_at` has passed, **When** overdue is computed, **Then** it is treated as due-now (`due_at = start_at`, or task creation time when `start_at` is NULL) — never silently skipped as the watchdog does today (`app/services/system_health_alert_service.py:110` excludes NULLs). |
| **OBS-S2-03** `[BE][T]` | **Given** a task whose `start_at` is in the future, **When** overdue is computed, **Then** it is NOT overdue regardless of `last_run_at`. |
| **OBS-S2-04** `[BE][T]` | **Given** interval `I`, **When** grace is computed, **Then** `grace = clamp(grace_percent × I, 60s, 30min)` and the task is overdue **only** when `now > due_at + grace`. Boundary tests: `now == due_at + grace` → NOT overdue; `now == due_at + grace + 1s` → overdue. |
| **OBS-S2-05** `[BE][T]` | **Given** a global `grace_percent` in `system_settings` (default 25) **and** a task whose `metadata_` contains `{"grace_percent": <n>}`, **When** grace is computed for that task, **Then** the per-task value wins; for tasks without the key the global value applies. |
| **OBS-S2-06** `[BE][T]` | **Given** the same DB state, **When** `GET /api/v1/system/health` and the watchdog `_eval_scheduled_tasks` each report overdue, **Then** they return the **identical set of task keys** — asserted by a test that drives both through one shared helper. The divergent inline queries at `app/api/v1/system/health.py:148` and `app/services/system_health_alert_service.py:110` are deleted, not patched. |
| **OBS-S2-07** `[BE][T]` | **Given** a disabled task that is far past `due_at`, **When** overdue is computed, **Then** it is NOT reported overdue by either surface. |

### Alert email content

| Id | Given / When / Then |
|----|---------------------|
| **OBS-S2-08** `[BE][T]` | **Given** two overdue tasks, **When** the watchdog fires the scheduled-task alert, **Then** the email body itemizes **each** task with: task key, human `name`, interval (e.g. "every 15 minutes"), `last_run_at` rendered as Malaysia wall-clock, lateness in human units (e.g. "23m late"), and a deep link to that task's run-log page (`/system-management/scheduled-tasks/{id}`). |
| **OBS-S2-09** `[BE][T]` | **Given** an overdue task, **When** lateness is rendered, **Then** it is measured from `due_at` (not from `due_at + grace`, not from `last_run_at`), so "23m late" means 23 minutes past when the run was owed. |
| **OBS-S2-10** `[BE][T]` | **Given** the alert already fired and the condition persists, **When** the watchdog runs again inside the cooldown, **Then** no duplicate email is sent (existing `health_alert_state` de-dup, `app/services/system_health_alert_service.py:52`); **and** when every task recovers, a recovery notice is sent exactly once. |
| **OBS-S2-11** `[BE]` | **Given** the current live DB, **When** the watchdog runs after this slice, **Then** zero tasks are reported overdue while the scheduler heartbeat is healthy — i.e. the standing false-positive is gone (verified against the local prod-copy DB). |

### FE — per-task grace

| Id | Given / When / Then |
|----|---------------------|
| **OBS-S2-12** `[FE]` | **Given** an admin on the scheduled-task detail page, **When** they open the edit form, **Then** a "Grace period (%)" field is present, shows the effective value with the global default as placeholder text, and accepts empty = "use global". |
| **OBS-S2-13** `[E2E]` | **Given** an admin, **When** they navigate **via the sidebar** (System Management → Scheduled Tasks → a task), set grace to 50, save, and reload, **Then** the value persists in `metadata_.grace_percent` and the network tab shows the `PUT /api/v1/system/scheduled-tasks/{id}` call. |
| **OBS-S2-14** `[FE][T]` | **Given** the grace field, **When** a non-numeric or negative value is entered, **Then** a validation message is shown and no request is sent. |

---

## S4 — WhatsApp round-trip latency SLA

*Measures user-sends-in-WhatsApp → reply accepted by Respond, and enforces a p99.*

### Timestamps + clock discipline

| Id | Given / When / Then |
|----|---------------------|
| **OBS-S4-01** `[EXT]` | **Given** the n8n save-incoming subworkflow (`UrETd-jm46tFj3Xw7w8vL`), **When** it posts to `/api/v1/external/chat-history`, **Then** `sent_at` carries the **raw Respond `message.timestamp`** (epoch ms, verbatim), NOT `new Date().getTime()`. |
| **OBS-S4-02** `[EXT]` | **Given** the n8n send subworkflow (`aoydkG1dbItXR5jXFEQsP`) and the save-incoming subworkflow, **When** either saves a row, **Then** `message_id` is populated on **both** directions. (Baseline: 4 of 1519 rows — effectively never.) |
| **OBS-S4-03** `[EXT]` | **Given** both save nodes, **When** a row is saved, **Then** `turn_id = {{ $execution.id }}` is stamped, identical for the incoming and outgoing rows of the same turn. |
| **OBS-S4-04** `[BE][T]` | **Given** an old n8n payload with **none** of `turn_id` / `respond_ts` / new fields, **When** it POSTs to `/api/v1/external/chat-history`, **Then** it still validates and inserts (schema gains OPTIONAL fields only; Pydantic `extra=ignore`) — no n8n deploy-ordering outage. |
| **OBS-S4-05** `[BE][T]` | **Given** an ingested row, **When** it is written, **Then** `ingest_at` is stamped from the **CRM server clock** while `sent_at` stays on Respond's clock, so webhook lag (`ingest_at − sent_at`) is diagnosable and is NOT part of the SLA measurement. |
| **OBS-S4-06** `[BE][T]` | **Given** an outgoing row, **When** latency is computed, **Then** both endpoints are on **Respond's clock** (t0 = incoming `sent_at`; t1 = the outgoing message's Respond-side `sent` timestamp), so measured latency contains **zero clock skew**. |

### Resolver scheduled task (no polling)

| Id | Given / When / Then |
|----|---------------------|
| **OBS-S4-07** `[BE][T]` | **Given** the new `chat_delivery_resolver` scheduled task (60s), **When** it runs, **Then** it selects `chat_histories` rows where `message_id IS NOT NULL AND (respond_ts IS NULL OR delivery_status IS NULL) AND resolve_attempts < 5`, capped at ~200 per run, ordered oldest-first. **Revised 2026-07-21** (was `respond_ts IS NULL` alone): `respond_ts` now lands at ingest via OBS-S4-26, so skipping on it would leave Delivery permanently blank on every ingested row. |
| **OBS-S4-08** `[BE][T]` | **Given** a selected row, **When** the resolver calls `RespondClient.get_message` (`app/services/integration_service.py:335`) with identifier `id:{contact_id}` and the row's `message_id`, **Then** on success it writes `respond_ts` (Respond `sent` timestamp) and `delivery_status`, and on later runs also `delivered_ts` / `read_ts` when present. |
| **OBS-S4-09** `[BE][T]` | **Given** a `404 / message not found`, **When** the resolver handles it, **Then** `resolve_attempts` is incremented and no `respond_ts` is written; **and** at `resolve_attempts == 5` the row is marked `delivery_status = 'not_sent'` and stops being selected. Not-found means **NOT SENT** — never "assume sent". |
| **OBS-S4-10** `[BE][T]` | **Given** a transport error / 5xx from Respond, **When** the resolver handles it, **Then** the run does not abort the whole batch; the row is retried on the next tick and the task run is logged with a partial-success summary. |
| **OBS-S4-11** `[FE][E2E]` | **Given** the resolver task, **When** an admin opens System Management → Scheduled Tasks **via the sidebar**, **Then** `chat_delivery_resolver` appears in the list with its run log — i.e. the enricher is itself observable (this is why it is a scheduled task, not per-row RQ jobs). |

### Turn pairing + SLA definition

| Id | Given / When / Then |
|----|---------------------|
| **OBS-S4-12** `[BE][T]` | **Given** an incoming and an outgoing row sharing a `turn_id`, **When** the turn is paired, **Then** latency = outgoing `respond_ts` − incoming `sent_at`. No time-window join is used. |
| **OBS-S4-13** `[BE][T]` | **Given** rows with `turn_id IS NULL` (proactive/broadcast sends), **When** the SLA is computed, **Then** they are **EXCLUDED from the denominator** — never heuristically paired, never guessed. |
| **OBS-S4-14** `[BE][T]` | **Given** an outgoing message that reaches `sent`, **When** the SLA clock is evaluated, **Then** it **STOPS at `sent`** (Respond accepted). `delivered` / `read` timestamps are captured and displayed but are **NOT** SLA'd — a phone-off recipient must not blow p99. |
| **OBS-S4-15** `[BE][T]` | **Given** messages `sent` but not `delivered` after 15 minutes, **When** metrics are computed, **Then** a separate `undelivered_over_15m` count is reported, distinct from the latency SLA. |
| **OBS-S4-16** `[FE]` | **Given** the SLA target (default **p99 ≤ 10s**), **When** an admin edits it in System Settings, **Then** it persists in `system_settings` and takes effect on the next evaluation without a deploy. |

### Alerting (on from day one — high-volume, business-critical)

| Id | Given / When / Then |
|----|---------------------|
| **OBS-S4-17** `[BE][T]` | **Given** the rolling **last 200 turns**, **When** recomputed every 60s and the p99 exceeds the target, **Then** a `whatsapp_latency_degraded` alert fires through the existing `health_alert_state` machinery with cooldown + a recovery notice on return to normal. |
| **OBS-S4-18** `[BE][T]` | **Given** a single turn exceeding **3× target (30s)**, **When** evaluated, **Then** a `whatsapp_stalled_turn` alert fires naming the `turn_id`, contact, and measured latency. |
| **OBS-S4-19** `[BE][T]` | **Given** an incoming message with **no outgoing row for its `turn_id` after 5 minutes**, **When** evaluated, **Then** a `whatsapp_no_reply` alert fires. |
| **OBS-S4-20** `[BE][T]` | **Given** fewer than a minimum sample of paired turns in the window, **When** p99 is evaluated, **Then** no degraded alert fires (no alerting off a 3-turn sample). |
| **OBS-S4-21** `[BE]` | **Given** any of the three alerts, **When** the email/in-app notice is rendered, **Then** it deep-links to the n8n execution via `turn_id` for triage. |

### Migration

| Id | Given / When / Then |
|----|---------------------|
| **OBS-S4-22** `[MIG]` | **Given** the existing `chat_histories` table (high volume), **When** the migration runs, **Then** it adds `respond_ts`, `delivery_status`, `delivered_ts`, `read_ts`, `resolve_attempts` (default 0), `turn_id`, `ingest_at` — all nullable/defaulted so no table rewrite lock — plus an index supporting the resolver sweep and one supporting turn pairing; and `alembic downgrade -1` cleanly reverses it. |
| **OBS-S4-23** `[MIG]` | **Given** ~1519 pre-existing rows, **When** the migration completes, **Then** they are left with NULL `turn_id` and are therefore correctly excluded from the SLA denominator (per OBS-S4-13) rather than back-filled with a guess. |

---

## S5 — Chat history admin UI + export + downloads purge

| Id | Given / When / Then |
|----|---------------------|
| **OBS-S5-01** `[BE][T]` | **Given** `chat_histories`, **When** it is registered in `app/services/list_query_registry.py` `ADAPTERS`, **Then** it exposes a `view_slug` and an `export_slug`, and `GET /api/v1/list-query/column-config/{listing_key}` round-trips column order/visibility for it. |
| **OBS-S5-02** `[FE]` | **Given** the chat-history DataGrid, **When** it renders, **Then** each row is one message with columns: time (Malaysia), contact (**resolved name + phone**), direction, message (truncated + `title`), latency (outgoing rows only), delivery status — with `tableLayout: { width: 'fixed', columnsResizable: true }`, `columnResizeMode: 'onChange'`, and an explicit `size` per column. |
| **OBS-S5-03** `[FE]` | **Given** any row, **When** the contact column renders, **Then** it shows a human name + phone and **never** the raw Respond contact id or any UUID (PRINCIPLES: no UUIDs in the UI). |
| **OBS-S5-04** `[BE][T]` | **Given** `chat_histories.contact_id` is the **Respond.io id STRING** (not `respond_contacts.id`), **When** names are resolved, **Then** the join is on the Respond-id column and rows with no matching contact fall back to the phone number without erroring. |
| **OBS-S5-05** `[FE][E2E]` | **Given** an admin, **When** they filter by date range (default **last 24h** on `sent_at`), contact, direction, and "breached only", **Then** the grid reflects each filter and the network tab shows the params built by `buildDataGridParams` (no hand-built `URLSearchParams`). |
| **OBS-S5-06** `[BE][T]` | **Given** a large result set, **When** the list is paged, **Then** pagination is **keyset on `(sent_at, id)`** using the existing `chat_histories` indexes, and page N+1 never repeats or skips a row across an insert. |
| **OBS-S5-07** `[FE][E2E]` | **Given** the grid, **When** a row is clicked, **Then** a side drawer opens with that contact's **threaded transcript centred on the selected message**, and this same drawer serves as the per-contact conversation view. |
| **OBS-S5-08** `[FE]` | **Given** no rows for the filter, **When** the grid and drawer render, **Then** each shows an explicit empty state with a next-step CTA — no hidden section. |
| **OBS-S5-09** `[BE][T]` | **Given** an export request, **When** it is created, **Then** a `user_downloads` row of kind `chat_history_export` is created and an RQ task enqueued; the task streams CSV **from a DB cursor** (constant memory, no row ceiling) and uploads via `storage_router` to `exports/chat-history/{download_id}/{filename}.csv`. |
| **OBS-S5-10** `[BE][T]` | **Given** any failure inside the export task, **When** it is caught, **Then** the task calls `mark_failed` and **never raises** into RQ's failed registry — matching the producer contract of `generate_complaint_pdf` (`app/tasks/export_tasks.py:18`). |
| **OBS-S5-11** `[FE]` | **Given** the My Downloads drawer, **When** a chat-history export appears, **Then** it renders a human label from a new `KIND_LABEL` entry (`components/my-downloads/DownloadRow.tsx:21`), not the raw kind string. |
| **OBS-S5-12** `[BE][T]` | **Given** the new `user_downloads_purge` scheduled task, **When** it runs, **Then** for **every** kind it deletes both the storage object and the row past the configured retention (default 30d), and a missing storage object does not abort the sweep. This closes a real existing gap — today nothing purges `user_downloads` and `complaint_pdf` files accumulate forever. |
| **OBS-S5-13** `[PERM]` | **Given** new permission slugs for chat-history **view** and **export**, **When** the migration runs, **Then** they are granted to existing `superadmin` / `admin` roles by a grant sweep (not seed-if-absent), and a user without the slug gets 403 on the API and does not see the sidebar entry. Message content is PII — it is gated. |
| **OBS-S5-14** `[E2E]` | **Given** an admin, **When** they reach the page **by clicking through the sidebar** from `/`, filter to last 24h, open a row drawer, and request an export, **Then** the export completes and downloads, with zero console errors. |
| **OBS-S5-15** `[FE]` | **Given** 375px and 1280px viewports, **When** the grid and drawer render, **Then** both are usable and non-clipped, and the drawer scrolls. |

---

## S1 — Health dashboard: date range, four-bucket classification, benign reclassification

| Id | Given / When / Then |
|----|---------------------|
| **OBS-S1-01** `[FE]` | **Given** the health dashboard, **When** it loads, **Then** a **global date-range picker** sits at the top of the page defaulting to **last 24h**, and every range-sensitive metric filters on the underlying records' `created_at`. |
| **OBS-S1-02** `[FE]` | **Given** point-in-time backlogs (Email Queue **Pending**, Scheduled Tasks **total**), **When** the range changes, **Then** those figures render **absolute and unchanged**, explicitly labelled "as of now" — they are not silently range-filtered. |
| **OBS-S1-03** `[BE][T]` | **Given** any integration channel, **When** outcomes are classified, **Then** exactly four buckets are produced — **Success / Failed / Benign / In-flight** — and `success + failed + benign + in_flight == total` for every channel (property-asserted). |
| **OBS-S1-04** `[BE][T]` | **Given** the live-data case `n8n_crm_chat_outbound` currently showing success 0, failed 0, total 13, **When** it is reclassified, **Then** the `pending` / `processing` / `sent` rows land in **In-flight** and are visibly rendered — today they are counted in the total but rendered nowhere. |
| **OBS-S1-05** `[BE][T]` | **Given** the `sla_management` writer that raises `"Conversation is already responded."` (`app/services/sla_service.py:3647`), **When** that idempotency race occurs, **Then** the **writer** logs a benign status (`idempotent_already_active`, the value already used at `app/api/v1/sla/sla_tracking.py:758`) instead of `failed`. Fix the writer, don't just mask on read. |
| **OBS-S1-05b** `[BE][T]` | **Given** `POST /conversation-sla-tracking/integration` (the endpoint n8n calls to open a conversation SLA), **When** the service refuses the input (e.g. "Respond contact not found for phone number: X"), **Then** the caller receives that refusal's own status — 400 / VALIDATION_ERROR — not 500 / INTERNAL_ERROR with the real message buried in the body. A genuine crash still returns 500, and a malformed body still returns 422. |
| **OBS-S1-06** `[BE][T]` | **Given** the 46 historical `sla_management` failed rows (all of which are this same race), **When** the dashboard reads them, **Then** a **per-channel benign-signature rule table** reclassifies them into **Benign** on read, so history stops screaming. |
| **OBS-S1-07** `[BE][T]` | **Given** a genuinely failed row whose error does not match any benign signature, **When** classified, **Then** it stays in **Failed** — the rule table is an allowlist of known-benign signatures, never a catch-all. |
| **OBS-S1-08** `[FE]` | **Given** the Email Queue card, **When** it renders, **Then** the already-computed `failed_last_24h` (`app/api/v1/system/health.py:107`) is shown alongside the all-time figure, e.g. **"2 in 24h (63 all-time)"** — the four current numbers are all-time totals, which is why 63 looked like a live incident. |
| **OBS-S1-09** `[FE][E2E]` | **Given** the dashboard reached **via the sidebar**, **When** an admin clicks a Failed count, **Then** they drill through to the filtered integration-log list for that channel/status/range. |
| **OBS-S1-10** `[FE]` | **Given** a channel with zero rows in the selected range, **When** it renders, **Then** an explicit empty state appears rather than a hidden row. |
| **OBS-S1-11** `[BE][T]` | **Given** many failed rows of the same underlying fault whose `error_message` differs only by embedded ids/timestamps, **When** the dashboard aggregates them, **Then** they collapse into **one signature with a summed count** — masking uuids, digit runs and ISO timestamps, and nothing else. |
| **OBS-S1-12** `[BE][T]` | **Given** two failures with identical prose but different `status_code` (e.g. 401 vs 403), **When** aggregated, **Then** they stay **separate signatures** — same words under a different HTTP code is a different problem to chase. |
| **OBS-S1-13** `[BE][T]` | **Given** rows classified **Benign** or **In flight**, **When** signatures are built, **Then** they are **excluded** — only `OUTCOME_FAILED` rows may appear as a fault to chase, or the classification work of OBS-S1-05..07 is undone at render time. |
| **OBS-S1-14** `[BE][T]` | **Given** an httpx failure carrying the boilerplate `"For more information check: <mdn url>"` suffix, **When** displayed, **Then** the suffix is trimmed — unless trimming would blank the message, in which case the original is kept. |
| **OBS-S1-15** `[FE][E2E]` | **Given** a channel with failures, **When** the card renders, **Then** the **top 3 distinct causes** appear inline beneath the channel row with per-cause count, status code and an **un-masked** sample message — so the cause is readable without navigating away. |
| **OBS-S1-16** `[FE][E2E]` | **Given** the admin has changed the dashboard date range, **When** they click a Failed count, **Then** the drill-down carries **that** range (not a hardcoded 24h), and the destination row count **equals** the number clicked. |
| **OBS-S1-17** `[BE][T]` | **Given** a failure signature, **When** its drill-down filter is built, **Then** it emits **every** stable substring of the message (volatile tokens removed), not just the longest — one term cannot separate two faults sharing a prefix. |
| **OBS-S1-18** `[BE][T]` | **Given** an `error_contains` term containing a LIKE wildcard (`%` or `_`), **When** filtering, **Then** it is escaped and matched literally. |
| **OBS-S1-19** `[FE][BE][T]` | **Given** a cause rendered on the card, **When** the admin clicks it, **Then** the log list is filtered by channel + status + range + `status_code` + all `error_contains` terms, and lands on **exactly** the count shown on the card. |
| **OBS-S1-20** `[FE][T]` | **Given** the log list opened with a cause filter, **When** it renders, **Then** a banner names the cause (code + terms) and offers **"Show all failures"** — the cause filter has no control in the filter panel, so without the banner the list would be silently narrowed. |

> Context (not an AC): `respond_io` historical failures are overwhelmingly 401/403 against obvious
> test contacts (`id:123456`, `55555`, `9999`). Noted so the reviewer does not mistake them for a
> live incident; no code change is required for them in this slice.

---

## S3 — `api_call_log` request telemetry

*Backend-first; one new FE list page.*

| Id | Given / When / Then |
|----|---------------------|
| **OBS-S3-01** `[MIG]` | **Given** the migration, **When** it runs, **Then** a new `api_call_log` table exists in `public` with: endpoint, method, source, actor, status_code, outcome, latency_ms, correlation_id, truncated request payload, truncated response payload, `created_at` — with indexes on `(created_at)`, `(source, created_at)`, and `(correlation_id)`. |
| **OBS-S3-02** `[BE][T]` | **Given** a request to **any** `/api/v1/external/*` route, **When** it completes (2xx, 4xx, or 5xx), **Then** middleware writes exactly one `api_call_log` row — **synchronously**, so a crash cannot lose the evidence for the incident being logged. |
| **OBS-S3-03** `[BE][T]` | **Given** a brand-new external endpoint added with **no per-endpoint logging code**, **When** it is called, **Then** it is logged — coverage is total by construction. (Baseline: only **3 of ~30** external endpoints log anything today: chat-history ingest, conversation-variables, ideation.) |
| **OBS-S3-04** `[BE][T]` | **Given** payloads larger than the cap, **When** stored, **Then** each of request/response is truncated to ~8KB with a visible truncation marker, and secrets (`x-api-key`, auth headers) are redacted. |
| **OBS-S3-05a** `[BE][T]` | **Given** an MCP-originated call to a route **outside** `/api/v1/external/*` (most MCP tools proxy ordinary CRM endpoints — the products catalogue is `/api/v1/master-data/*`), **When** it carries `X-Source`, **Then** it is logged. Scoping on the path prefix alone misses the majority of MCP traffic. A request to the same route **without** `X-Source` is NOT logged, so internal UI traffic stays out. |
| **OBS-S3-05** `[BE][T]` | **Given** an MCP-originated call carrying `X-Source: mcp`, `X-Correlation-Id`, `X-Tool-Name`, **When** logged, **Then** `source = 'mcp'` and the tool name and correlation id are recorded — today the backend **cannot** distinguish MCP from n8n (same shared `EXTERNAL_API_KEY`, no headers). |
| **OBS-S3-06** `[BE][T]` | **Given** a call with no `X-Source`, **When** logged, **Then** `source` falls back to a defined default (e.g. `n8n`/`unknown`) and the row is still written. |
| **OBS-S3-07** `[EXT][T]` | **Given** the MCP client (`sorento_crm_mcp/sorento_crm_mcp/http_client.py`), **When** it issues a request, **Then** it sends the three headers, and its client-side `elapsed_ms` (measured at `http_client.py:122` but today only printed to stdout) is joinable to the server-side span via `correlation_id`. |
| **OBS-S3-08** `[BE]` | **Given** the previously-unlogged external endpoints — view-link, next-assignee, presigned-url, rag, memory, contact-access-types, packing-lists, spo-allocations, grn, promotions, forms, stock-inquiries, purchase-requests, team-members, work-calendar, respond-contacts, portal-tokens, it-support/tickets, and the `*-attachments` routes — **When** each is exercised once, **Then** each produces an `api_call_log` row. |
| **OBS-S3-09** `[BE][T]` | **Given** `integration_log`, **When** this slice ships, **Then** it is **NOT** extended. It remains a **work-queue** record (`retry_count`, `max_retry_allowed`, `next_retry_at`) with a UUID `business_id` that chat-ingest already fakes (`app/api/v1/external/chat_history.py:107`). Telemetry and retryable business integrations stay separate. |
| **OBS-S3-10** `[BE][T]` | **Given** the new `api_call_log_prune` scheduled task, **When** it runs, **Then** it NULLs payloads on rows older than **30d** and DELETEs rows older than **180d**; both thresholds are configurable in `system_settings`. |
| **OBS-S3-11** `[BE][T]` | **Given** the logging middleware, **When** the log write itself fails, **Then** the API response is unaffected (log failure is warned, never raised into the request path). |
| **OBS-S3-12** `[FE][E2E]` | **Given** an admin reaching the new page **via the sidebar** under System Management, **When** they filter by source, endpoint, outcome, date range, and correlation id, **Then** the grid reflects each filter, uses `buildDataGridParams`, and renders an explicit empty state when nothing matches. |
| **OBS-S3-13** `[BE][T]` | **Given** a burst of external traffic, **When** the middleware writes synchronously, **Then** the added p95 latency per request is measured and recorded in the test report (the accepted cost of not losing evidence). |

---

## S6 — Timezone rendering standard

| Id | Given / When / Then |
|----|---------------------|
| **OBS-S6-01** | **Given** the DB stores **naive UTC**, **When** this slice ships, **Then** no backend or schema change is made — this is a **frontend-only** bug. |
| **OBS-S6-02** `[FE]` | **Given** an API timestamp string with no timezone suffix (e.g. `"2026-07-02 09:05:00"`), **When** it is passed through `new Date(...)`, **Then** JS parses it as **browser-local** and produces the wrong instant **before any formatter runs**; the correct call is `formatDateTimeInMalaysia(rawString)` (`sorento_crm_frontend/lib/helpers.ts:432`) on the raw string. This id is satisfied by a vitest case that pins both the wrong and the right behaviour. |
| **OBS-S6-03** `[FE][E2E]` | **Given** the Administrative Users grid (`/user-management/users`) reached **via the sidebar**, **When** a user whose stored `last_sign_in_at` is `09:05` UTC is displayed, **Then** **Last Sign In** reads **5:05 pm** MYT, not 9:05 am. *(Repro required first: both current render sites already call `formatDateTimeInMalaysia` on what looks like a raw string — see the plan's S6 note. The AC is the observed output, not a presumed line edit.)* |
| **OBS-S6-04** `[FE][T]` | **Given** the ESLint config, **When** `npm run lint` runs, **Then** a rule bans `format*(new Date(...))` and raw `toLocaleString` / `toLocaleDateString` / `toLocaleTimeString` on API timestamps, with a **shrinking allowlist** file grandfathering the existing sites — the same playbook as the SearchableSelect standard (`eslint.config.mjs`, `eslint-dropdown-allowlist.mjs`). |
| **OBS-S6-05** `[FE]` | **Given** a **new** violating site added after this slice, **When** lint runs, **Then** it is flagged (allowlist covers only pre-existing files). |
| **OBS-S6-06** `[FE]` | **Given** the burn-down, **When** each module batch is swept, **Then** the allowlist shrinks and its size is reported as the metric. Measured baseline: **103** `format*(new Date(` sites + **~36–39** raw `toLocale*` sites (≈139 total). |

---

## Cross-cutting

| Id | Given / When / Then |
|----|---------------------|
| **OBS-X-01** `[PERM]` | **Given** every new permission slug in this feature, **When** its migration runs, **Then** existing provisioned roles receive the grant (DoD gate #3) — no slice silently 403s. |
| **OBS-X-02** `[MIG]` | **Given** every new column on a table that already has rows, **When** the migration runs, **Then** a backfill/default is applied idempotently (JOIN-based "set where mismatch", not "update where NULL") or the NULL semantics are explicitly specified as correct (as in OBS-S4-23). |
| **OBS-X-03** | **Given** every new backend column that must reach the FE, **When** it is added, **Then** it is present in **both** the schema and any manual dict builder (DoD gate #4). |
| **OBS-X-04** | **Given** retention, **When** configured, **Then**: `api_call_log` payload → NULL @ 30d, row → DELETE @ 180d; `user_downloads` → file + row DELETE @ 30d. All thresholds live in `system_settings` and are user-editable. |
| **OBS-X-05** | **Given** any handoff to the user, **When** they are asked to test on :3000, **Then** a **production build** (`npm run build && npm start`) is running — never a dev server. |
| **OBS-X-06** | **Given** every slice, **When** Phase 2 completes, **Then** its ids are keyed PASS / FAIL / DEFERRED in `monitoring-enhancement-test-report.md`. |

### S4 addendum — `respond_ts` derived at ingest (added 2026-07-21)

Found on production after S4 shipped: `turn_id` was pairing rows correctly, but **every**
`respond_ts` was NULL, so `chat_history_query` dropped every turn and the admin grid showed
"—" in Latency and Delivery on every row. The resolver — the only writer of `respond_ts` —
was failing every call (`resolve_attempts` climbing 1→5 on production rows).

Root cause of the blank column is that the SLA clock had a single point of failure. Respond
mints `messageId` as the message's epoch-**microsecond** timestamp, so the authoritative
clock already arrives in the ingest payload and never needed an HTTP round trip.

| Id | Given / When / Then |
|----|---------------------|
| **OBS-S4-26** `[BE][T]` | **Given** an ingest payload carrying a Respond `message_id`, **When** `POST /external/chat-history/messages` inserts the row, **Then** `respond_ts` is derived from the id (µs epoch) and written in the same INSERT — no resolver round trip required for the SLA clock. |
| **OBS-S4-27** `[BE][T]` | **Given** an inbound WhatsApp id whose microseconds are exactly zero (`1784602116000000`), **When** it is parsed, **Then** the whole-second value is accepted — that granularity is Respond's, not a rounding artefact. |
| **OBS-S4-28** `[BE][T]` | **Given** an id that is not a plausible timestamp (a sequence id like `1234556`, a millisecond epoch, a non-numeric string, or NULL), **When** it is parsed, **Then** `respond_ts` stays NULL and the row sits out of the SLA — never a guessed value. A short id read as µs lands in 1970 and would otherwise inject a 56-year round trip into the p99. |
| **OBS-S4-29** `[BE][T]` | **Given** a derived timestamp more than 1 day from the row's `sent_at`, **When** it is validated, **Then** it is rejected. Guards the two classic misparses (µs read as ms → year 58xxx; ms read as µs → 1970), which miss by decades, while tolerating `sent_at`'s known drift of seconds. |
| **OBS-S4-30** `[BE][T]` | **Given** two ingested rows sharing one `turn_id`, **When** the admin grid is queried, **Then** `latency_seconds` is populated on the **outgoing** row only and the incoming row stays blank. |
| **OBS-S4-31** `[BE]` | **Given** the historical rows whose `respond_ts` never resolved, **When** `scripts/backfill_chat_respond_ts.py` runs, **Then** it derives `respond_ts` with the *same* parser as the live path, and clears `delivery_status='not_sent'` **only** on rows it could derive a timestamp for (Respond minting an id proves the message existed, so `not_sent` was the resolver giving up). Idempotent: a second run reports zero changes. |
| **OBS-S4-32** `[BE]` | **Given** a resolver 404, **When** it is handled, **Then** it is logged. Previously silent, which made a resolver 404-looping on every row indistinguishable from one that never ran — the reason this defect stayed invisible. |
