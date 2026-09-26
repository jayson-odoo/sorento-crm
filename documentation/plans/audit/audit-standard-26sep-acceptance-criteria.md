# UAC: audit standard, slice S0 (event model and emitter) - issue #1281

Plan: `PLAN-audit-standard-26sep.md` alongside. Tags: `[BE]` backend test, `[T]` migration or
tooling test. S0 has no screen, so there is no `[FE]` or `[E2E]` line; S2 carries those.

## Journey

Actor: an admin (or, later, an auditor) who has to answer "who changed this, when, from where, and
why" about any record, days or months after the fact.

1. Something looks wrong on a record (a price, a role, a PO status). The admin opens the audit
   trail for it (today the global audit log screen; after S2 the History drawer on the record).
2. The system already knows everything needed: the record, the rows that roll up to it, and every
   change made to any of them, whether it came from the UI, a portal contact, an integration key,
   a background import or a scheduler tick. Nobody had to remember to add audit code to the
   endpoint.
3. Each change names the person (or the key and the person it acted for), the channel it came
   through, the fields that changed (old to new, secrets masked), the business verb when there is
   one, and the reason when one was given.
4. The admin can follow "everything in this request" and "everything this action caused",
   including the job it queued, because they share a request id and a correlation id.
5. The admin ends holding a trail they can trust: nobody, including the application itself, can
   edit or delete it outside the retention job.

## S0 acceptance criteria

### Default-on emission

- **AC-S0-01 [BE]** Given a mapped class with no `__audit_track__` and no `__audit_skip__`, when
  a row is created, updated and deleted through the ORM, then three `audit_logs` rows are written
  (CREATE, UPDATE, DELETE). (Journey 2)
- **AC-S0-01b [BE]** Given a new row whose code never set its primary key (a Python-side
  `default=uuid4` only runs at INSERT), then its CREATE row is still written; a DB-generated key
  (serial / identity) gets its CREATE row after the INSERT. Found in the build: main silently
  dropped these CREATE rows. (2)
- **AC-S0-02 [BE]** Given a class declaring `__audit_skip__ = "<reason>"`, when a row is written,
  then no audit row is written; and every `__audit_skip__` value is a non-empty string. (2)
- **AC-S0-03 [BE]** Given an UPDATE that changes one column, then `old_values` / `new_values`
  hold only that column's key. CREATE and DELETE still hold the full snapshot. (3)
- **AC-S0-04 [BE]** Given an UPDATE whose only change is a touch column (`last_used_at`,
  `last_sign_in_at`, `updated_at`, ...), then no audit row is written. (3)

### Redaction

- **AC-S0-05 [BE]** Given a write that changes `users.password`, `system_settings.smtp_password`
  or an `*_ciphertext` / `*_token` / `key_hash` column, then the audit row holds the key with the
  value `"[redacted]"` and the raw value appears nowhere in the row; the same holds for an explicit
  `log_audit` call and for a bulk UPDATE. (3)

### Bulk DML

- **AC-S0-06 [BE]** Given `query(Model).filter(...).update({...})` on an audited table, then one
  UPDATE audit row per matched row is written with the old and new value of each SET column. (2)
- **AC-S0-07 [BE]** Given `query(Model).filter(...).delete()` (and a Core `delete(Model)` through
  `Session.execute`), then one DELETE audit row per matched row is written with the old snapshot.
  (2)
- **AC-S0-08 [BE]** Given a bulk statement matching more rows than the cap, then exactly `cap`
  per-row audit rows plus one summary row naming the remaining count are written. (2)
- **AC-S0-09 [BE]** Given a bulk statement on a skipped table, or with the entity type in
  `session.info["skip_audit_entity_types"]`, then no audit row is written. (2)

### Request context, principal and source

- **AC-S0-10 [BE]** Given a request through `LoggingMiddleware` whose sync dependency calls
  `set_audit_context(user, ip)` (the `get_current_user_or_api_key` shape), when the sync endpoint
  writes an audited row, then the row's `user_id` is that user, not NULL. Red on main. (3)
- **AC-S0-11 [BE]** Given an API-key request through the real `get_current_user_or_api_key`, then
  the audit row carries `principal_type = api_key`, `principal_id` = the integration id,
  `user_id` = its act-as user, and `source` derived from the integration type (`automation` ->
  `n8n`, `mcp` -> `mcp`, else `external_api`). (3)
- **AC-S0-12 [BE]** Given a JWT request, then `principal_type = user`, `principal_id = user_id`,
  `source = ui`. Given impersonation, then `user_id` = the real admin and `on_behalf_of_user_id` =
  the target. (3)
- **AC-S0-13 [BE]** Given a portal write (actor contact set), then `principal_type = contact`,
  `principal_id` = the contact, `source = portal`. (3)
- **AC-S0-14 [BE]** Given an inbound `X-Trace-Id` longer than 64 characters, then the stored
  `trace_id` is at most 64 characters and the write succeeds. An inbound `X-Correlation-Id`
  becomes `correlation_id` only once an integration key authenticates; otherwise
  `correlation_id` equals the request id, so an ordinary caller cannot stitch its writes into
  another action (security review S2). (4)
- **AC-S0-15 [BE]** Given a write with no context at all (a script), then `principal_type =
  system` and the write succeeds. Given a scheduler tick (`scheduler_session`), then
  `principal_type = scheduler`, `source = scheduler` and a request id is set. (2)

### Worker

- **AC-S0-16 [BE]** Given a job enqueued through `enqueue_job` inside a request context, then
  `job.meta["audit_context"]` carries the user, correlation id and on-behalf-of. When the job runs
  (`ForkSafeWorker.perform_job` or `run_sync_rq_jobs`), its audited writes carry that user and
  correlation id, `principal_type = worker`, `source = import` on the `imports` queue (else
  `worker`), and `trace_id` = the job id. (4)
- **AC-S0-17 [T]** `worker.py`'s startup registers the audit listeners. (2)

### Review round 1 (security-reviewer and reviewer on PR #1299)

- **AC-S0-26 [BE]** Given a row of a table with no `company_id` whose `__audit_parent__` or NOT
  NULL foreign key points at a company-scoped parent, then every audit row for it (flush, bulk,
  after-flush) carries the parent's company; a nullable reference never pins a global row. (5)
- **AC-S0-27 [BE]** `api_call_log` is skipped; secret keys are redacted at every depth of a JSON
  value; `push_subscriptions.auth` / `p256dh` and `*_webhook_url` / `*_webhook` are redacted; a
  guard test fails when a secret-looking column on an audited table is neither redacted nor named
  harmless. (3)
- **AC-S0-28 [BE]** A DB-generated key (market_segments) gets its CREATE row; an attribute set
  after the object expired keeps its real old value; a bulk statement with named bind parameters
  still runs; `UPDATE ... FROM` criteria itemise each row once; the pre-select locks the matched
  rows. (2, 3)
- **AC-S0-29 [BE]** A scheduled task's Run now names the user who pressed it;
  `/api/v1/external/chat-history` is not tagged `chatbot`. (3)

### Business verbs and reason

- **AC-S0-18 [BE]** Given a service method decorated `@audit_event("x.y.confirm", entity=...,
  ids="ids", reason="reason")` that updates an audited row, then that row's audit record carries
  `event = x.y.confirm` and the passed reason; the context's event and reason are restored after
  the call, including when it raises. (3)
- **AC-S0-19 [BE]** Given the decorated method flushes nothing for an id, then one `EVENT` row is
  written for that id with the event and reason. Given `record(db, event=..., entity_type=...,
  entity_id=...)`, then one `EVENT` row is written with the current context stamped. (3)

### Root entity

- **AC-S0-20 [BE]** Given a child class declaring `__audit_parent__ = "<fk column>"`, then its
  rows carry `root_entity_type` = the parent's audit entity type and `root_entity_id` = the FK
  value; a class with no parent carries its own type and id as the root. (1)

### Append-only

- **AC-S0-21 [BE]** Given any `audit_logs` row, an `UPDATE`, `DELETE` or `TRUNCATE` raises from
  Postgres; after `SET LOCAL sorento.audit_maintenance = 'on'` in the same transaction it
  succeeds. Holds on a `create_all`-built table (CI, blank schema) and after the migration. (5)
- **AC-S0-21b [BE]** Rows written in one transaction keep their write order: `changed_at`
  defaults to `clock_timestamp()`, not `now()` (the transaction start, which gave every row of
  one request the same timestamp and a random history order). Found in the build. (1)
- **AC-S0-22 [BE]** Given the `audit` module is purged, then `purge_audit` deletes no audit rows
  and reports 0. (5)

### API

- **AC-S0-23 [BE]** `GET /api/v1/audit/logs/` returns `request_id`, `correlation_id`, `event`,
  `source`, `reason`, `principal_type`, `principal_id`, `on_behalf_of_user_id`,
  `root_entity_type`, `root_entity_id` on each item (`response_model` would otherwise drop them).
  (4)

### Migration

- **AC-S0-24 [T]** `aud_0001_audit_standard_s0` chains onto the current single head, its id is at
  most 32 characters, its upgrade adds the nine columns, widens the action CHECK with `EVENT` and
  installs the trigger; its downgrade removes them. The graph has one head. (5)
