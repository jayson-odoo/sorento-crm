# PLAN: one append-only audit backbone for every function (issue #1281)

Status: S0 in build on `feat/audit-standard-s0` (Track: full - a migration and an auth-surface
change). S-1 (security fixes) runs in its own lane on `fix/audit-log-security-holes`. S1, S2, S3
not started.
Plan created: 2026-09-26 (from the investigation report on #1281, comment 5846914028, sections 7
to 10, investigated at `51d30ccc5`).
Domain: audit (CORE, not a module: every install needs a trail; the `audit` App Store key keeps
gating only the read screens).
UAC: `audit-standard-26sep-acceptance-criteria.md` alongside.

## Owner rulings

- **26 Sep 2026 23:45 MYT, decision 1 (security fixes first):** "yeah". The three section-6
  findings ship now as their own lane (S-1), ahead of S0.
- **26 Sep 2026 23:45 MYT, decision 2 (evolve `audit_logs` or build `audit_events`):** "the
  recommended standard should be applied now, we must do the right thing now". Evolve
  `audit_logs` in place; no second table. The orchestrator reads this ruling as authorising the
  whole recommended standard (section 7 below) as a sliced build, S0 first.

Every other decision in the report is still open and is listed as a grill question at the end.
Where S0 has to pick a side to be buildable at all (decisions 3 and 11), it builds the report's
recommendation under ruling 2 and says so; the grill question asks the owner to confirm.

## Measured facts (origin/main `dc10a1afb`, 26 Sep 2026)

- `audit_logs` (`app/models/audit.py`) is written by a global `before_flush` listener
  (`app/services/audit_service.py`), registered in the API only (`app/main.py`). 42 of 331 mapped
  classes set `__audit_track__ = True`.
- The actor lives in three separate contextvars (`app/audit_context.py`): a `(user, ip,
  effective)` tuple, `trace_id`, `actor_contact_id`. Every auth dependency calls `.set()`.
  `get_current_user_or_api_key` is a sync `def` (`app/dependencies.py`), so FastAPI runs it on a
  copied context in a threadpool and its `.set()` is lost to the endpoint.
- UPDATE rows snapshot every column (`_old_new_from_dirty`), changed or not. `User` carries no
  `__audit_columns__`, so `password` is copied on every user update (S-1 finding 6.1).
- The action vocabulary is enforced by a CHECK constraint that exists only in migrations
  (`271_audit_action_allow_import`): `CREATE, READ, UPDATE, DELETE, IMPORT`. `create_all` (CI,
  `scripts/bootstrap_env.py`, the blank test schema) does not build it.
- Bulk ORM DML (`query().update()/delete()`, ORM `update()/delete()`) never reaches
  `before_flush`. 124 + 13 sites.
- `worker.py` registers the company-scope and spec listeners but never
  `register_audit_listeners`. Jobs are enqueued through `app.services.queue_service.enqueue_job`
  (all but 5 direct `.enqueue` sites) and run in `ForkSafeWorker.perform_job` or, for the
  in-process drain, `run_sync_rq_jobs`.
- Scheduler ticks all open their session through `app.scheduler.task_scheduler.scheduler_session`.
- Integration keys resolve to a seeded service user per integration (`integration_seed.py`:
  `n8n` type `automation`, `sorento-mcp` type `mcp`, `foundryx-esb` type `autocount_esb`). The
  in-app assistant reaches the backend through the MCP server, so its writes arrive as the MCP
  integration; nothing carries the end user yet.
- `module_purge_service.purge_audit` deletes every audit row when the `audit` module is
  uninstalled with purge.
- Row volume per day on the production copy: **not measurable in this cloud lane** (no prod
  copy). The query to run before merge is in "Measurement" below.

## The standard (report section 7)

### 7.1 One append-only event model: `audit_logs`, evolved

New columns (S0), all nullable so every existing row and reader keeps working:

| Column | Meaning |
|---|---|
| `root_entity_type`, `root_entity_id` | The record an operator opens to see this change. A child model declares `__audit_parent__ = "<fk column>"`; the parent's audit entity type is read from the FK target. A model with no parent rolls up to itself, so "history of record X" is one predicate on the root pair. |
| `event` | Business verb, dotted (`scm.po.confirm`, `settings.general.update`, `auth.login_failed`). NULL = plain CRUD. |
| `principal_type`, `principal_id` | Who authenticated: `user`, `contact`, `api_key` (id = `integrations.id`), `worker`, `scheduler`, `system`. |
| `on_behalf_of_user_id` | Whose intent it was when that differs from `user_id`. S0 fills it for impersonation (the target; the real admin stays in `user_id`). The API-key and assistant cases need a trusted header and wait for grill question G7. |
| `source` | `ui`, `portal`, `chatbot`, `mcp`, `n8n`, `external_api`, `import`, `worker`, `scheduler` (and `assistant` once G7 lands). Derived server side, never from `X-Source`. |
| `reason` | Free text or a reason code. |
| `correlation_id` | One per business action across processes; a job inherits its request's. Taken from an inbound `X-Correlation-Id` (the header `api_call_log` already reads) or defaults to the request id. |

Unchanged: `trace_id` IS the request id (one per HTTP request or job run), now length-clamped to
64 on ingest and returned by the API as `request_id`. `action` keeps the CRUD vocabulary plus
one new value, `EVENT`, for a side effect that changed no row (a download, a send, a login).

**Append-only is enforced by Postgres.** A `BEFORE UPDATE OR DELETE` row trigger and a
`BEFORE TRUNCATE` statement trigger raise unless the transaction has run
`SET LOCAL sorento.audit_maintenance = 'on'`. The migration creates it for existing databases; an
`after_create` DDL hook on the model creates it wherever `create_all` builds the table (CI
bootstrap, the blank test schema), so the two cannot drift (lesson 90). The retention job (S3) and
any scrub migration set the flag. Module purge stops deleting audit rows.

Decision on the "application role" wording in the report: this deployment runs one database role,
so a second role is machinery for a problem we do not have; the `SET LOCAL` flag is the report's
own named alternative. Trigger to revisit: a second writer role appears.

### 7.2 Emission: one hook, one decorator, no per-endpoint code

1. **Default-on.** The `before_flush` listener audits every mapped class unless it declares
   `__audit_skip__ = "<reason>"`. `__audit_columns__` still narrows a table. `__audit_track__`
   stays on the 42 classes as a no-op marker (removing it is churn with no behaviour change).
2. **Changed keys only on UPDATE.** CREATE and DELETE stay full snapshots. An UPDATE whose only
   changed keys are touch columns (`updated_at`, `last_used_at`, `last_sign_in_at`,
   `last_seen_at`, `last_activity_at`, `last_synced_at`, `synced_at`, `last_run_at`,
   `storage_checked_at`) writes nothing. Measured writers: `integrations.last_used_at` (every
   API-key call), `users.last_sign_in_at` (every login), `integration_references.last_synced_at`
   (every sync, even of an unchanged record; found by the suite), `scheduled_tasks.last_run_at`
   (every heartbeat), catalogue syncs, the storage audit job.
3. **Bulk ORM DML via `do_orm_execute`.** For an audited table, an ORM or Core `update()` /
   `delete()` issued through `Session.execute` pre-selects the matching primary keys (and the old
   values of the SET columns, or the whole row for a delete), capped at 500 rows per statement,
   and writes one audit row each (plus one `description="... N more rows"` summary row beyond the
   cap). SET values that are SQL expressions read `"[expression]"`. Raw `text()` DML and
   `bulk_*_mappings` are not seen; S3 allowlists the 16 sites by name.
4. **One mutable request context.** `AuditContext` (a dataclass) replaces the three contextvars.
   `LoggingMiddleware` puts a fresh object in the contextvar per request; every auth dependency
   MUTATES it. A sync dependency on a copied context mutates the same object, which is the fix for
   the API-key attribution loss (report section 1, inferred). The old function API
   (`set_audit_context`, `get_audit_context`, `set_trace_id`, `set_actor_contact_id`, ...) stays as
   thin wrappers, so none of its 20 callers change.
5. **Worker inherits context.** `worker.py` registers the audit listeners. `enqueue_job` stamps
   the current context into `job.meta["audit_context"]`; `ForkSafeWorker.perform_job` and
   `run_sync_rq_jobs` restore it before the task runs, with `principal_type = worker`,
   `source = import` on the `imports` queue (else `worker`), `request_id = job id`, and the
   request's `correlation_id`, `user_id` and `on_behalf_of_user_id` kept. The deliberate
   `skip_audit_for` / `skip_audit_entity_types` plus one coarse IMPORT row stays for imports.
   Scheduler ticks get `principal_type = scheduler`, `source = scheduler` and a fresh request id in
   `scheduler_session`.
6. **Redaction in the listener.** Keys named `password`, `token`, `key_hash`, `code_hash`,
   `credentials_json`, or ending `_password`, `_secret`, `_token`, `_ciphertext`, or starting
   `api_key`, never reach `old_values` / `new_values`: the value reads `"[redacted]"` so the fact
   of the change survives. Applied inside `log_audit` and the bulk path, so explicit callers are
   covered too. Overlap with S-1: S-1(a) redacts `password` and scrubs existing rows. S0 needs
   the wider denylist regardless, because default-on starts auditing `system_settings`,
   `integration_api_keys`, `respond_workspaces`, `ai_assistant_configs`, `view_tokens` and more.
   When S-1 lands, the two denylists merge into this one function; the scrub migration stays
   S-1's.
7. **Business verbs: `@audit_event` and `audit.record()`.**
   `@audit_event("scm.po.confirm", entity="purchase_orders", ids="ids", reason="reason")` sets
   `event` (and `reason` from the named argument) on the context for the duration of the call, so
   every row the hook writes inside it carries the verb; for an id in `ids` that got no row, it
   writes one `EVENT` row itself. `record(db, event=..., entity_type=..., entity_id=...)` is the
   one explicit call for a non-service caller. The 38 `log_audit` call sites move over in S1.
8. **Reason is a body field**, passed by the service to the decorator; S0 ships the plumbing,
   S1 adds the fields on the decision-6 routes.

The bespoke domain logs stay product data and are linked by `correlation_id` (decision 8 is open;
nothing in S0 depends on it).

### 7.3 Retention (S3)

24 months hot in Postgres, monthly gzip JSONL export to R2 with a manifest row, then delete under
the maintenance flag. Business events deleted from the archive after 7 years, security and access
events after 2. S0 deletes nothing. Partition trigger: more than about 10M rows, or the per-record
history query over 1s at p95.

### 7.4 Screens (S2)

Per-record History drawer in every detail page's `PageHeader` (entity or root entity = this
record), per-user Activity tab replacing `user-management/logs`, global search with server-served
entity types and event / source / principal / request / correlation / reason filters, audited
export. `audit.logs.view` enforced on the backend, IP addresses only to its holders. No UUIDs.

### 7.5 Interlock with #1280

`user_id` is the human. Once #1280 provisions a user for a contact, portal writes stamp both
`user_id` and `contact_id` for one release; history is never rewritten and resolves contact to
user at read time. #1280's auth paths emit `auth.*` events through `record()` from their first
commit, which makes S0 a prerequisite of #1280's first auth slice (grill G9).

## PR-CHECKLIST addition (report section 8, lands in S3)

```markdown
## Audit trail (every state-changing endpoint)
- [ ] Every new or changed POST / PUT / PATCH / DELETE route leaves an audit event: its
      tables are audited (default-on; any `__audit_skip__` names its reason), or the service
      method carries `@audit_event("<domain>.<entity>.<verb>")` for a side effect that
      flushes nothing (send, download, export, login)
- [ ] Approve, confirm, reject, cancel, void, publish and send carry a business `event`
      name, not only a CRUD row, so they are searchable by verb
- [ ] Actions on the "reason required" list (owner decision 6) take `reason` in the body and
      the test asserts it lands on the audit row
- [ ] No new `query().update()` / `.delete()` / `text()` DML / `bulk_*_mappings` on an
      audited table outside the reviewed allowlist (`tests/test_audit_coverage.py`)
- [ ] Work moved into an RQ job is enqueued through the context-carrying helper, so the
      job's rows name the requesting user and share the request's correlation id
- [ ] No secret column (password, token, key, hash) reaches `old_values` / `new_values`
- [ ] A test asserts the event: actor, `source`, `event`, and the changed field in the diff,
      for the happy path of each new state-changing route
- [ ] A new detail page shows the History drawer in its `PageHeader`
```

Backed by `tests/test_audit_coverage.py` (S3): fails when a mapped table is neither audited nor
`__audit_skip__` with a reason, or a bulk / raw DML site on an audited table is off the allowlist.

## Sliced rollout (report section 9)

| Slice | Contents | Track, size |
|---|---|---|
| S-1 security hotfix | Redact `password` + scrub existing JSON; gate `/audit/logs/` and `/audit/activity` on a backend permission and company-scope `/activity`; remove or lock down `POST /user-management/system-logs/`. | Full (migration + auth), S. Own lane. |
| **S0 event model and emitter (this PR)** | Columns + migration + `EVENT` action; mutable `AuditContext`; default-on with `__audit_skip__`; changed-keys UPDATE; `do_orm_execute` bulk capture; worker listener + `job.meta` carry; scheduler context; `@audit_event` + `record()`; reason plumbing; principal / on-behalf / source derivation for JWT, API key, portal, impersonation; append-only trigger; module purge keeps audit rows; API returns `request_id`, `correlation_id`, `source`, `event`, `reason`, `principal_type`, `principal_id`, `on_behalf_of_user_id`, root entity. | Full, L. |
| S1 backfill the gaps | Roles / permissions / company grants (`set_user_roles` as a diff); system settings; SCM PO confirm, GR, bulk delete; GRN; core `sales_orders` ingest with a stored verdict; auth events; downloads and exports; sends to customers; project PO / schedule / SO / order inquiry verbs. | Full, L (may split S1a / S1b). |
| S2 screens | History drawer, per-user Activity, global search upgrades, `audit.logs.view` + grant sweep. | Full, M. |
| S3 the gate | PR-CHECKLIST section, `tests/test_audit_coverage.py`, retire `system_logs` and `import_logs`, retention + R2 archive job. | Small fix apart from any archive migration, S to M. |

Dependencies: S-1 first; S0 blocks S1, S2 and #1280's auth slice; S1 and S2 in parallel; S3 last.

## S0 design details

- Migration `aud_0001_audit_standard_s0` (id under 32 chars): nine columns, three indexes
  (`event`, `correlation_id`, `(root_entity_type, root_entity_id)`), CHECK widened with `EVENT`,
  trigger function `audit_logs_append_only()` plus the two triggers. Downgrade drops all of it.
- Skip-list (`__audit_skip__`), by reason class: the trails themselves (`audit_logs`,
  `activity_events`, `module_install_events`, `import_logs`, `integration_log`,
  `scheduled_task_runs`, `system_logs`, `conversation_sla_event_log`,
  `workflow_submission_transition_logs` is NOT skipped because the report wants its history kept
  when a submission is deleted); derived or recomputed data (embeddings, SCM analytics and reorder
  runs, findability runs, translation memory, AI assistant traces / spans / usage / messages);
  queues and job progress (`import_jobs`, `import_job_rows`, `email_outbox`,
  `notification_deliveries`, `notifications`, `media_extraction_job`, `embedding_queue`,
  `sla_form_actions`, dealer-kit export requests and flyer readings, `user_downloads`); timers
  and cursors (`conversation_sla_tracking`, `agent_team_round_robin_cursors`,
  `health_alert_state`, `contact_media_usage`, `conversation_frames`); sessions and one-time
  secrets (`user_sessions`, `portal_otp_codes`, `verification_tokens`); per-user UI preferences
  (`user_list_column_configs`, `saved_views`, `user_quick_access`, `report_views`); message logs
  (`chat_histories`, `chatbot.turns`, `entity_conversation_messages`). The exact list with each
  reason is in the models; S3's coverage test is what keeps it honest.
- Principal and source: JWT = `user` / `ui`; impersonation = `user` / `ui` with
  `on_behalf_of_user_id` = target; API key = `api_key` + integration id, `user_id` = the
  integration's service user, source by integration type (`automation` -> `n8n`, `mcp` -> `mcp`,
  anything else -> `external_api`) except `/api/v1/external/chat*` -> `chatbot`; portal = `contact`
  / `portal`; worker, scheduler as above; nothing set = `system`.

## Measurement (before the default-on flip merges)

Run on the production copy and paste the result into this plan:

```sql
SELECT date_trunc('day', changed_at) AS day, count(*)
FROM audit_logs WHERE changed_at > now() - interval '30 days'
GROUP BY 1 ORDER BY 1;
SELECT count(*) FROM audit_logs;
SELECT pg_size_pretty(pg_total_relation_size('audit_logs'));
```

The flip multiplies writers from 42 classes to about 280; the skip-list takes the known
high-churn tables. If the post-merge daily count exceeds 10x the pre-merge figure, the next step is
narrowing the loudest table with `__audit_columns__` or `__audit_skip__`, not reverting the
default.

## Tests (red first, then green)

See the UAC for the per-AC list. Files: `tests/test_audit_standard_s0.py` (listener, context,
bulk, decorator, redaction, trigger, worker carry), `tests/test_audit_api_key_attribution.py`
(the sync-dependency attribution red test), `tests/test_migration_aud_0001_audit_standard.py`.

## Out of scope for S0

S-1's work (scrub migration, read-route permission gate, `system_logs` POST), any screen, any
reason field on a route, the retention job, the trusted on-behalf-of header, backfilling any
history (decision 10).

## Grill questions for the owner

1. **Default-on auditing (decision 3).** S0 flips to default-on with the reasoned skip-list above
   (built under ruling 2). Confirm, or keep opt-in? Recommendation: default-on.
2. **Measurement gate.** The daily row count on the prod copy could not be taken in the cloud
   lane. Run the three queries above before merge, or accept measuring after deploy with the 10x
   narrowing rule? Recommendation: run them before merge.
3. **Retention (decision 4).** 24 months hot then R2; delete business events after 7 years and
   security / access events after 2; `chatbot.turns` envelopes after 12 months. Confirm 7 years
   with the accountant (Companies Act 2016).
4. **Record reads (decision 5).** Record downloads, exports and customer-data sends; do not
   record page views or plain GETs. Confirm.
5. **Reason required (decision 6).** Mandatory on reject, cancel, void, unacknowledge, a
   confirmed-document delete (PO, SO, GRN), a permission or role change, a price-floor override;
   optional elsewhere, typed inline next to the D7 countdown. Confirm the list.
6. **Who sees the trail (decision 7).** Global search and per-user Activity: superadmin, admin
   and `audit.logs.view`; per-record History: anyone who can view the record; IP addresses:
   `audit.logs.view` only. Confirm.
7. **Trusted on-behalf-of header (report 7.5 item 4).** Let the chatbot and MCP keys, flagged per
   integration, pass the end user's id so the row reads "MCP key on behalf of Jane"? This is a new
   auth surface and needs a security review. Recommendation: yes, in S1 behind a per-integration
   flag.
8. **Fold bespoke logs into `audit_logs` (decision 8).** Recommendation: no; link by
   `correlation_id`, retire only `system_logs` and `import_logs`, audit the SLA event log's manual
   POST / DELETE.
9. **Sequencing against #1280 (decision 9).** S-1 and S0 land before #1280's first auth slice.
   Confirm.
10. **Reconstruct history (decision 10).** Recommendation: no; the trail starts at S0 and the S1
    PR records the date each gap closed.
11. **API-key attribution bug (decision 11).** Built in S0 with a red test first (the mutable
    context is S0's foundation). Confirm it stays in S0.
12. **API-key `user_id`.** An integration's act-as user is a seeded service user, not a person,
    so S0 keeps it in `user_id` (existing screens name it) and leaves `on_behalf_of_user_id` empty
    until question 7 lands. Confirm, or show the integration name instead of the service user?
