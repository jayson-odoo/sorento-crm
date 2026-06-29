# System Management — Data reference for admins

This page documents the **System Management** operational logs and configuration tables so admins (and power users) can answer troubleshooting / "what happened?" questions accurately. The recurring questions are operational, not commercial:

* "Which emails failed today?"
* "Which imports errored, and on which rows?"
* "Is a scheduled task stuck?"
* "Which Respond.io sends 401'd?"
* "Was this notification ever actually sent?"

> **No MCP tools.** Unlike commercial / inventory / procurement, System Management exposes **no MCP tools** to the AI assistant — there is no `system_*` read tool the assistant can call. This page is an **admin reference for power users** working the list pages directly (filter + sort + Export). The assistant cannot list these rows for you; it can only explain where to look and what the status codes mean. Every page below has an **Export** button (xlsx) for offline analysis.

> **Reading notes**
> * **Timestamps are stored naive UTC; most list pages render Malaysia time (UTC+8).** Be explicit about the timezone when quoting a time, and remember a "today" window in the DB is UTC midnight-to-midnight, not local.
> * **No UUIDs in answers.** Resolve `business_id`, `user_id`, `notification_id` etc. to a human-readable reference (entity number, email, person's name) before replying.
> * **Three separate message-delivery logs exist** — Email Outbox, Outgoing Mails, and Respond Outbox. They are not the same table and answer different questions. The distinctions are spelled out below; getting them wrong sends an admin to the wrong page.
> * **Get the status codes exact.** Each log has its own status vocabulary. They are quoted verbatim per entity — do not assume a shared "sent / failed" set across pages.

The pages and their menu paths:

| Page | Menu path | Backing table |
|------|-----------|---------------|
| Import Jobs | [Import Jobs](/system-management/import-jobs) | `import_jobs` |
| Import Logs | [Import Logs](/system-management/import-logs) | `import_logs` |
| Integration Logs | [Integration Logs](/integration-management/integration-logs) | `integration_log` |
| Scheduled Tasks | [Scheduled Tasks](/system-management/scheduled-tasks) | `scheduled_tasks` (+ `scheduled_task_runs`) |
| Outgoing Mails | [Outgoing Mails](/system-management/outgoing-mails) | `notification_deliveries` (email channel) |
| Email Outbox | [Email Outbox](/system-management/email-outbox) | `email_outbox` |
| Respond Outbox | [Respond Outbox](/system-management/respond-outbox) | view over `integration_log` |
| Email Event Configs | [Email Event Configs](/system-management/email-event-configs) | `email_event_configs` |
| Email Templates | [Email Templates](/system-management/email-templates) | `email_templates` |
| Automation | [Automation](/system-management/automation) | `automations` (+ `automation_runs`) |
| Running Numbers | [Running Numbers](/system-management/numbering-rules) | `document_numbering_rules` |
| Lookup Sets | [Lookup Sets](/master-data-management/lookup-sets) | `lookup_sets` (+ options / keywords / bindings) |
| Respond.io Workspaces | [Respond.io Workspaces](/system-management/respond-workspaces) | `respond_workspaces` |

---

## Import Jobs — `import_jobs`

The **lifecycle tracker for a background (RQ) import job**: progress counts and the job's run state. One row per upload that was enqueued to the worker (Excel imports, GRN/SPO/product/stock/order-tracking imports, attachment bulk import).

> **Import Jobs vs Import Logs — read this first.** They are two different tables for two different moments.
> * **Import Jobs** (`import_jobs`) = the *RQ job* and its live progress (`status`, `processed_rows`, `started_at`/`completed_at`). Answers "is it still running / did the job finish / did it crash?".
> * **Import Logs** (`import_logs`) = the *post-mortem record* of an import run — the row-level outcome (`successful` / `created` / `updated` / `failed` / `skipped`) plus the `errors` / `warnings` JSON. Answers "which rows failed and why?".
> * They are linked: `import_logs.import_session_id` equals the job's `job_id`. Not every import_log has a job (services like stock/order import write a log directly), and a failed job may write a log with all-zero counts plus the error.

**Key fields**

| Field | Meaning |
|-------|---------|
| `job_id` | RQ job id (the worker's handle; also the `import_session_id` on the matching import log). |
| `job_type` | What kind of import — e.g. `stock_import`, `order_import`, `order_tracking_import`, `product_import`, `spo_import`, `grn_listing_import`, `grn_lines_import`, `delivery_order_detail_import`, `warehouse_import`, `attachment_bulk_import`. |
| `status` | Run state (enum below). |
| `user_id` | Who started it. **The list is scoped to the current user — see the caveat below.** |
| `filename` | Uploaded file name. |
| `total_rows` / `processed_rows` / `successful_rows` / `failed_rows` / `skipped_rows` | Progress + outcome counts. |
| `result` (JSON) / `error` (text) | Final result payload / failure message. |

**Status values (exact — `JobStatus` enum):** `pending`, `queued`, `started`, `finished`, `failed`, `cancelled`.
*A "succeeded" job's status is `finished`, not "success" or "completed".* A job can be cancelled while in `pending` / `queued` / `started`.

**Date columns:** `created_at` (enqueued), `started_at`, `completed_at`, `updated_at`. Columns shown: **Type, Status, Filename, Total Rows, Processed, Success, Failed, Skipped, Created At, Started At, Completed At, Updated At**.

**Available filters:** **Filter by type** (`job_type`), **Filter by status** (`status`). Per-row actions: **Refresh this job**, **Cancel** (only while `pending` / `queued` / `started`).

> **Caveat — Import Jobs is per-user.** The list endpoint filters `user_id = current_user`, so an admin sees **only their own** import jobs, not everyone's. "Show all failed imports across the team today" cannot be answered from this page — use **Import Logs** (not user-scoped) for a tenant-wide view of import outcomes.

**Example questions**

* "Is my stock import still running or did it finish?" (`status` = `started` vs `finished`)
* "Which of my imports failed today?" (`status` = `failed`, today by `created_at`)
* "How many rows did job X process vs fail?" (`processed_rows` / `failed_rows`)
* "Cancel the stuck product import I just started." (Cancel action, allowed while `started`)
* "Did the GRN lines upload error out — what's the message?" (`status` = `failed`, read `error`)
* "List my queued imports waiting on the worker." (`status` = `queued` / `pending`)
* "Which file did job X import?" (`filename`)

---

## Import Logs — `import_logs`

The **persisted outcome record of an import run** — written at the end of an import (by the worker job *and* by direct service imports like stock/order). This is the table for **row-level errors and warnings**, and it is **not** user-scoped (any admin sees all of them).

**Key fields**

| Field | Meaning |
|-------|---------|
| `import_session_id` | Links to the import job's `job_id` (when there was a job). |
| `entity_type` | What was imported — e.g. `stock`, `order`. |
| `entity_table` | Target table — e.g. `stock`, `orders`. |
| `import_type` | Pipeline label — e.g. `EXCEL_IMPORT`, `BULK_IMPORT`. |
| `filename` | Source file (may be null for service-driven imports). |
| `total_rows` / `successful_rows` / `created_rows` / `updated_rows` / `failed_rows` / `skipped_rows` | Outcome counts. |
| `warnings` (JSON) / `errors` (JSON) | Per-row warnings and errors — **the load-bearing field for "why did this fail?"** Each entry typically carries the row number, the error, and the offending data. |
| `summary` (JSON) | Import-type-specific extras (e.g. `system_adjusted_to_zero`, `master_rows` / `tracking_rows`). |
| `imported_by` | Who ran it. |
| `duration_ms` | How long it took. |

**Status values:** **none** — there is no status enum. Outcome is read from the **counts** (`failed_rows > 0` = had failures) and the **`errors` JSON**. A fully-failed job writes a log with all-zero counts and the error in `errors`.

**Date columns:** `imported_at` (**default sort, newest first**). Columns shown: **Entity, Filename, Type, Success, Skipped, Failed, Description, Imported By, Created At, Duration**.

**Available filters:** **Filter by entity type** (`entity_type`) only.

**Example questions**

* "Which rows failed in the last stock import, and why?" (open the row, read `errors` JSON)
* "How many records were created vs updated in the latest order import?" (`created_rows` / `updated_rows`)
* "Were any rows skipped on the warehouse import?" (`skipped_rows`, plus `warnings`)
* "Show every stock import this week." (`entity_type` = `stock`, by `imported_at`)
* "Which products got zeroed by the last full-snapshot stock import?" (`summary.system_adjusted_to_zero`, errors detail)
* "Who ran the order import that had failures, and how long did it take?" (`imported_by`, `duration_ms`)
* "Find the import log for job X." (`import_session_id` = the job's `job_id`)

---

## Integration Logs — `integration_log`

The **system-wide integration audit trail**: every inbound/outbound call to an external integration (n8n webhooks, Respond.io sends, SLA callbacks). The **Respond Outbox** (below) is a filtered, prettified view of these same rows.

**Key fields**

| Field | Meaning |
|-------|---------|
| `integration_channel` | Which integration — e.g. `respond_io`, `n8n`, SLA channels, `integration_log_update`. |
| `business_table` / `business_id` | The CRM record this call relates to. **`business_id` is a UUID** (resolve before quoting). |
| `external_reference` | External id (for Respond sends this is the contact's `respond_io_id`). |
| `direction` | `inbound` or `outbound`. |
| `endpoint` / `http_method` | The URL + verb called. |
| `status_code` | HTTP status of the attempt (e.g. `200`, `401`, `404`, `500`). |
| `error_code` / `error_message` | Failure detail. |
| `request_payload` / `response_payload` (+ headers) | Full bodies, for debugging. |
| `retry_count` / `max_retry_allowed` | Retry budget (default max `3`); a **Retry** action appears when `status = failed` **and** `retry_count < max_retry_allowed`. |
| `next_retry_at` | When an auto-retry is due. |
| `correlation_id` / `created_by` | Tracing / actor. |

**Status values (exact):** `pending`, `processing`, `success`, `failed` (column default `pending`).
*(Some rows also carry an HTTP `status_code` — e.g. a `failed` row with `status_code = 401` is an auth failure on the integration.)*

**Date columns:** `created_at` (**default sort, newest first**), `processed_at`. Columns shown: **Channel, Business Table, Business ID, Status, Retries, Created, Processed**.

**Available filters:** **Search logs…** (matches `request_payload` / `external_reference`), **Status** (All Status / Pending / Processing / Success / Failed), **Channel** (All Channels / n8n / SLA Management / SLA Tracking (create) / SLA Tracking (update) / SLA Escalation), **Table** (All Tables / Attachments / Conversation SLA Tracking / Conversation SLA Event Log). Plus `business_id` via API.

**Example questions**

* "Which Respond.io sends failed today?" (`integration_channel` = `respond_io`, `status` = `failed`)
* "Show the 401s on outbound integrations." (`status` = `failed`, open rows with `status_code` = `401`)
* "What did n8n send back for attachment X?" (filter by `business_table`/`business_id`, read `response_payload`)
* "List failed integration calls that still have retries left." (`status` = `failed`, `retry_count < max_retry_allowed`)
* "Retry the failed webhook for this complaint." (Retry action on the row)
* "What's stuck in `processing`?" (`status` = `processing`)
* "Show all SLA escalation callbacks this week." (`integration_channel` = SLA Escalation, by `created_at`)

---

## Scheduled Tasks — `scheduled_tasks` (+ `scheduled_task_runs`)

Configurable background jobs driven by the in-process scheduler (e.g. the **email outbox drainer**, Respond contacts sync, integration-log retry, SLA ticks). Each task has a config row plus a history of run rows.

**Key fields (task)**

| Field | Meaning |
|-------|---------|
| `key` | Stable identifier (e.g. `respond_contacts_sync`). |
| `name` / `description` | UI label + context. |
| `enabled` | Whether the scheduler runs it. |
| `interval_unit` / `interval_value` | Cadence — `interval_unit` ∈ `seconds` / `minutes` / `hours` / `days`. |
| `timezone` | Schedule timezone (default `UTC`). |
| `start_at` | Optional first-run anchor. |
| `next_run_at` | When it's due to run next. |
| `last_run_at` | When it last ran. |
| `last_status` / `last_error` | Outcome of the most recent run. |

**Key fields (run — `scheduled_task_runs`):** `started_at`, `finished_at`, `status`, `duration_ms`, `summary` (JSON, e.g. `{"scanned": 10, "created": 2, "failed": 0}`), `error`.

**Status values (exact — both `last_status` and run `status`):** `started`, `success`, `failed`, `skipped`. (`last_status` is null until the first run.)

**Date columns:** `next_run_at`, `last_run_at` (task); `started_at`, `finished_at` (run). Columns shown: **Name, Key, Enabled, Frequency, Next Run, Last Run, Last Status**. The list returns **all** tasks (no status filter); drill into a task for its **runs**, and use **Run now** to trigger immediately.

> **Stuck-task detection.** A task is suspect when:
> * `enabled = true` but `next_run_at` is well in the past and not advancing — the scheduler may be down (check the backend process / `ENABLE_SCHEDULER`).
> * `last_status = started` with a `last_run_at` long ago and no newer run finishing — a run began and never completed (worker died mid-run).
> * `last_status = failed` repeatedly — read `last_error` and the latest run's `error` / `summary`.
> Related: the upload-activity drawer has its own sweeper that kills `sent` rows older than 10 minutes — that is a *different* mechanism from these scheduled tasks; don't conflate the two when chasing "stuck" items.

**Example questions**

* "Is the email drainer running, and when did it last run?" (`enabled`, `last_run_at`, `last_status`)
* "Which scheduled tasks failed on their last run?" (`last_status` = `failed`, read `last_error`)
* "When does the Respond sync run next?" (`next_run_at`)
* "Has any task been stuck in `started` for hours?" (run `status` = `started`, old `started_at`, no `finished_at`)
* "Run the integration-log retry task now." (Run now)
* "How long does the drainer take per run, and what did it process?" (run `duration_ms`, `summary`)
* "Which tasks are disabled?" (`enabled` = No)

---

## Outgoing Mails — `notification_deliveries` (email channel)

The **email delivery record for in-app notifications**. Each row is the *email-channel delivery* of a notification (joined to the notification + recipient user). This answers "did this user's notification email go out?".

> **Outgoing Mails vs Email Outbox.** Outgoing Mails is the **per-notification delivery record** (one row per notification's email delivery). Email Outbox is the **actual SMTP send queue** that every outbound email passes through — broader than notifications (auth emails, attachment-linkage emails, etc.). When the drainer sends an email-outbox row that came from a notification, it **writes back** to the matching Outgoing Mails row (sets it `sent` / `failed`). So a notification email appears in **both**: Email Outbox (the queue + attempts) and Outgoing Mails (the delivery outcome). For "why didn't it actually send?" the richer page is **Email Outbox** (attempts, `error_message`, `cancel_reason`).

**Key fields**

| Field | Meaning |
|-------|---------|
| `to_email` | Recipient (resolved from the notification payload or the user's email). |
| `subject` | The notification title. |
| `body` | Email content (notification body / `body_text` / `body_html`). |
| `status` | Delivery state (enum below). |
| `error_message` | Why it failed. |
| `notification_type` / `source_entity_type` / `source_entity_id` / `event_type` | Linkage back to the originating notification, for deep links / troubleshooting. |

**Status values (exact — `NotificationDelivery.status`):** `pending`, `sent`, `failed`.

**Date columns:** `created_at` (**default sort, newest first**), `sent_at`. Columns shown: **Queued At, To, Subject, Content, Status, Sent At, Error**.

**Available filters:** **Status** (All statuses / Pending / Sent / Failed), **search** (recipient email or subject).

**Example questions**

* "Did user X get their notification email?" (search the email, check `status` = `sent` + `sent_at`)
* "Which notification emails failed today?" (`status` = `failed`, by `created_at`, read Error)
* "What's stuck pending delivery?" (`status` = `pending`)
* "Show notification emails about complaint Y." (search subject / `source_entity_type`)
* "When was the approval email to manager Z sent?" (search email, `sent_at`)

---

## Email Outbox — `email_outbox`

The **single chokepoint for all outbound email**. Every outgoing email — notifications, auth flows, attachment-linkage, automation sends — is one row here, drained by the **email outbox drainer** scheduled task (the only producer of SMTP traffic). This is the **richest page for "why didn't an email send?"** because it carries attempts, backoff, and cancel reasons.

**Key fields**

| Field | Meaning |
|-------|---------|
| `event_key` | Which email event (maps to an Email Event Config). |
| `recipient_email` / `recipients_json` | Primary recipient + cc/bcc payload. |
| `subject` / `body_text` / `body_html` / `from_name` | Content. |
| `status` | Send state (enum below). |
| `priority` | Drain order (lower drains first; default `10`). |
| `scheduled_for` | Earliest send time (pushed into the future on rate-limit deferral / backoff). |
| `sent_at` | When it actually sent. |
| `attempt_count` / `max_attempts` | Tries vs cap (default `5`). |
| `error_message` | Last failure / rate-limit reason. |
| `cancel_reason` | Why a row was cancelled — `event_disabled`, `max_attempts_exceeded`, `cancelled_by_admin`. |
| `coalesce_key` | Dedup key — pending rows with the same key merge into one email. |

**Status values (exact — drainer-driven):** `pending`, `sending`, `sent`, `failed`, `cancelled`.
* `pending` → waiting to drain (also where a **rate-limited or backed-off** row sits, with `scheduled_for` pushed forward — it does *not* get a distinct status).
* `sending` → mid-attempt. `sent` → delivered. `failed` → hit `max_attempts` (`cancel_reason = max_attempts_exceeded`). `cancelled` → killed (event disabled, or by admin).

> **Note:** the Status filter dropdown also offers **Deferred**, but the drainer never writes a `deferred` status — a rate-deferred row stays `pending` with a future `scheduled_for`. Filtering by Deferred returns nothing. (Flagged for audit below.)

**Date columns:** `created_at` (**default sort, newest first**), `scheduled_for`, `sent_at`. Columns shown: **Queued At, Event, To, Subject, Status, Priority, Attempts, Scheduled, Sent At, Error, Actions**.

**Available filters:** **Status**, **`event_key`**, **search** (recipient or subject). Per-row actions: **View**, **Retry** (re-queues a failed/cancelled row → back to `pending`), **Cancel** (`cancel_reason = cancelled_by_admin`).

**Example questions**

* "Which emails failed to send today?" (`status` = `failed`, by `created_at`, read Error + `cancel_reason`)
* "Why didn't the approval email go out — was the event switched off?" (`cancel_reason` = `event_disabled` → check Email Event Configs)
* "Show emails stuck pending past their scheduled time." (`status` = `pending`, `scheduled_for` in the past)
* "How many attempts did this email make before failing?" (`attempt_count` / `max_attempts`)
* "Retry the failed welcome email." (Retry action)
* "List all emails for event `sla_assignment` this week." (`event_key` filter)
* "Were two identical reminders collapsed into one?" (`coalesce_key`)
* "Which emails are mid-send right now?" (`status` = `sending`)

---

## Respond Outbox — view over `integration_log`

A **read-only, prettified view of the Respond.io / WhatsApp messages the system sent** — the same `integration_log` rows where `integration_channel = 'respond_io'` and `direction = 'outbound'`, parsed into readable columns (message text or template, the linked entity, who sent it, the final button URL).

> **Memory rule — every Respond send is logged on success AND failure.** A 401'd send (e.g. local testing with intentionally-wrong workspace creds) still writes a row here. So an empty Respond Outbox means *nothing was attempted*, not "all succeeded". A closed-window send that fell back to a template logs as **template**, not text — the `sent_as` column shows the truth.

**Key fields**

| Field | Meaning |
|-------|---------|
| `contact_name` / `contact_phone` / `contact_identifier` | Recipient, resolved from `respond_contacts` by `respond_io_id` (= `external_reference`). |
| `sent_as` | `text` or `template`. |
| `message_text` | The actual message (template body with `{{1}}…` filled in). |
| `template_name` | Template used (when `sent_as = template`). |
| `button_url` | The final assembled URL-button link the contact would tap — surfaces a malformed double-host link. |
| `business_table` / `business_id` | The linked complaint / stock inquiry / purchase request (`business_id` is a UUID = the source record; for notification-driven sends it is the `notification.id`). |
| `status` / `status_code` / `error_message` / `response_payload` | Outcome (`status_code` e.g. `401` for a bad workspace key). |
| `created_by` | Who triggered the send. |

**Status values (exact — same vocabulary as Integration Logs):** `success`, `failed`, `pending`, `processing`.

**Date columns:** `created_at` (**default sort, newest first**). Columns shown: **Sent At, Contact, Type, Message / Template, Linked, Status**.

**Available filters:** **Status** (All statuses / Success / Failed / Pending / Processing), **`business_table`**, **search** (message text or contact). Per-row action: **View**.

> **Memory rule — Respond sends use the workspace key.** A `401` here almost always means a bad/placeholder **workspace** API key (`respond_workspaces.api_key_ciphertext`), not the deprecated env `RESPOND_API_KEY`. Check the workspace on the [Respond.io Workspaces](/system-management/respond-workspaces) page.

**Example questions**

* "Which WhatsApp sends failed today and why?" (`status` = `failed`, read `error_message` / `status_code`)
* "Did the complaint reply reach the contact?" (filter `business_table` = complaints, check `status` = `success`)
* "Show sends that went out as a template (window was closed)." (`sent_as` = `template`)
* "Is this contact's portal link malformed?" (inspect `button_url` for a double-host)
* "List all 401'd Respond sends." (`status` = `failed`, rows with `status_code` = `401`)
* "Who sent the message to contact X?" (`created_by`, resolve to a name)

---

## Email Event Configs — `email_event_configs`

Per-event **kill switches + rate/priority overrides** for the email pipeline. Rows are **seeded from `EMAIL_EVENT_REGISTRY` at startup**; admins toggle/override without a redeploy. These gate the Email Outbox: disabling an event makes the drainer **cancel** matching rows (`cancel_reason = event_disabled`).

**Key fields:** `event_key` (PK), `display_name`, `description`, `enabled` (the kill switch), `rate_per_window_override`, `window_seconds_override`, `priority_override`, `coalesce_window_seconds_override`.

**Status values:** none — `enabled` is a boolean (on/off).

**Date columns:** `created_at`, `updated_at`.

**Available filters:** none (static table). Columns shown: **Event, Enabled, Rate / window override, Window seconds override, Coalesce seconds override, Actions**. Editing is **inline** (toggle + override inputs, **Save overrides**) — no modal.

**Example questions**

* "Is the SLA assignment email switched on?" (`enabled` for that `event_key`)
* "Which email events are currently disabled?" (`enabled` = off — explains `event_disabled` cancels in Email Outbox)
* "Has anyone overridden the rate limit on event X?" (`rate_per_window_override` / `window_seconds_override`)
* "Why are emails for event Y being cancelled?" (event disabled here)

---

## Email Templates — `email_templates`

Designable HTML emails with Jinja2 placeholders, referenced by automations and notification flows.

**Key fields:** `code` (unique), `name`, `description`, `subject`, `body_html`, `body_text`, `variables_schema` (JSON), `is_active`, `created_by_user_id`.

**Status values:** none — `is_active` boolean (**Active** = Yes/No).

**Date columns:** `created_at`, `updated_at`. Columns shown: **Code, Name, Subject, Active, Updated**. Create/edit via **modal**; toolbar **Add template**; there is a **preview** action.

**Example questions**

* "Which email templates are inactive?" (`is_active` = No)
* "What's the subject line of template `code`?" (`subject`)
* "Which template does automation X use?" (cross-reference Automation → Template)
* "When was template Y last edited?" (`updated_at`)

---

## Automation — `automations` (+ `automation_runs`)

Rule-driven scheduled email sends — a **trigger** + a **template** + a **recipient rule**, run manually or daily. (Today's only scheduled trigger is `days_before_promotion_end`.)

**Key fields (automation):** `name`, `description`, `enabled`, `trigger_type`, `trigger_config` (JSON), `action_type` (default `send_email`), `email_template_id`, `recipient_config` (JSON), `group_matches`, `schedule_type` (`manual` / `daily`), `run_time`, `timezone` (default `Asia/Kuala_Lumpur`), `last_run_at`, `last_status`, `last_error`, `next_run_at`.

**Key fields (run — `automation_runs`):** `run_mode` (`manual` / `scheduled`), `started_at`, `finished_at`, `status`, `duration_ms`, `recipients_attempted`, `recipients_delivered`, `summary`, `error`.

**Status values (exact — run `status`):** `running`, `success`, `partial`, `failed`. (`partial` = some recipients delivered, some failed.) The automation's `last_status` mirrors the latest run.

**Date columns:** `last_run_at`, `next_run_at` (automation); `started_at`, `finished_at` (run). Columns shown: **Name, Trigger, Schedule, Template, Enabled, Last status, Next run**. Per-row **Run** (shows "Run queued: X recipient(s) attempted"), Edit, Delete; **Add automation** via modal.

**Example questions**

* "Which automations failed or partially failed on their last run?" (`last_status` = `failed` / `partial`)
* "How many recipients did automation X reach last run?" (`recipients_delivered` / `recipients_attempted`)
* "When does the promotion-expiry automation run next?" (`next_run_at`, `schedule_type` = `daily`)
* "Which automations are disabled?" (`enabled` = No)
* "Run automation Y now." (Run action)
* "Read the error from the last failed automation run." (run `error` / `summary`)

---

## Running Numbers — `document_numbering_rules`

Configurable running-number rules per document type (e.g. purchase request, sponsorship form). One row per `doc_type`; **edit-only** (no add/delete — rules are seeded).

**Key fields:** `doc_type` (unique, e.g. `purchase_request`, `sponsorship_form`), `enabled`, `prefix_template` (e.g. `PR-{year}-`), `number_digits` (default `4`), `next_value`, `start_value`, `reset_policy` (`none` / `yearly` / `monthly`), `last_reset_key` (e.g. `2026` or `2026-03`).

**Status values:** none — `enabled` boolean.

**Date columns:** `created_at`, `updated_at`. Columns shown: **Document type, Enabled, Prefix, Digits, Next value, Reset**. Edit via **modal** (PATCH by `doc_type`).

**Example questions**

* "What's the next purchase-request number going to be?" (`prefix_template` + `next_value` padded to `number_digits`)
* "Does the sponsorship-form numbering reset yearly?" (`reset_policy`)
* "Is numbering enabled for doc type X?" (`enabled`)
* "When did this counter last reset?" (`last_reset_key`)

---

## Lookup Sets — `lookup_sets` (+ options / keywords / bindings)

Generic master-data dropdown sets. A **set** holds **options** (the choices) and is attached to one or more table columns via **bindings**; options can carry **keywords** for fuzzy / NLP matching.

**Key fields**

| Table | Fields |
|-------|--------|
| `lookup_sets` | `set_key`, `name`, `description`, `is_active`, `tenant_id`. |
| `lookup_options` | `set_id`, `value`, `label`, `sort_order`, `is_active`, `description`. |
| `lookup_option_keywords` | `option_id`, `keyword`, `locale` — alternate phrasings for matching. |
| `lookup_bindings` | `set_id`, `table_name`, `column_name` — **where the set is used** as the dropdown source. |

**Status values:** none — `is_active` boolean (**Active** / **Inactive**).

**Date columns:** `created_at`, `updated_at`. Columns shown: **Set key, Name, Options (count), Bindings (count), Active**. Create/edit set via **modal**; options and bindings are managed in the set's editor.

**Example questions**

* "Which lookup sets are inactive?" (`is_active` = Inactive)
* "Where is set X used?" (its **bindings** — `table_name` / `column_name`)
* "How many options does set Y have?" (Options count)
* "Which option values exist for set Z?" (its `lookup_options.value` / `label`)
* "Which sets aren't bound to any column yet?" (Bindings count = 0)

---

## Respond.io Workspaces — `respond_workspaces`

Respond.io workspace configuration (multi-workspace per deployment). **The per-workspace API key here is what every Respond send uses** — the env `RESPOND_API_KEY` is a deprecated last-resort fallback.

**Key fields:** `space_id`, `name`, `api_key_ciphertext` (encrypted workspace key), `base_url`, `whatsapp_number` (E.164, drives the portal wa.me escape hatch), `is_active`, `is_default` (at most one default — DB-enforced).

**Status values:** none — `is_active` (**Active** / **Inactive**) + `is_default` (**Default** badge).

**Date columns:** `created_at`, `updated_at`. Columns shown: **Name, Space ID, Base URL, WhatsApp, API Key, Status, Default**. Add/Edit/Delete; **Set default** inline when not already default.

**Example questions**

* "Which workspace is the default sender?" (`is_default`)
* "Is workspace X active?" (`is_active`)
* "What's the WhatsApp number behind this workspace?" (`whatsapp_number`)
* "A Respond send 401'd — is the workspace key wrong?" (this page holds the key the send path actually uses)

---

## Cross-entity notes

* **Tracing one email end-to-end:** an in-app notification → its delivery shows in **Outgoing Mails** (`notification_deliveries`); the actual SMTP send + attempts live in **Email Outbox** (`email_outbox`); the drainer writes the outcome back to the Outgoing Mails row. For "why didn't it send", start at Email Outbox (`status`, `error_message`, `cancel_reason`), then check **Email Event Configs** if `cancel_reason = event_disabled`.
* **Tracing one WhatsApp send:** **Respond Outbox** (readable view) sits on top of **Integration Logs** (`integration_log`, raw request/response). A `401` → check **Respond.io Workspaces** (the workspace key).
* **Tracing one import:** **Import Jobs** for the run state (per-user), **Import Logs** for the row-level errors (tenant-wide), linked by `job_id` = `import_session_id`.
* **The drainers/syncs themselves** are **Scheduled Tasks** — if emails/WhatsApp/imports are globally not moving, check that the relevant scheduled task is `enabled` and its `last_run_at` is recent.
* **`business_id` is always a UUID** on Integration Logs / Respond Outbox — resolve to the entity number before quoting; for notification-driven Respond sends it equals `notification.id`.
* **Times are naive UTC, rendered Malaysia time** on the pages — state the timezone when quoting a timestamp.

## See also

* [Troubleshoot a failed notification (email or WhatsApp)](troubleshoot-failed-notifications.md)
</content>
</invoke>
