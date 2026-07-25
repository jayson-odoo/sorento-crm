# Test Inventory & Regression Guard Map

Generated 2026-07-21. Snapshot of what the suite actually guards, what it does not,
and why a full regression run currently costs ~1 hour.

## 1. Headline

| Suite | Files | Tests | Runtime | Green? | Runs in CI? |
|---|---|---|---|---|---|
| Backend pytest | 232 | 1,991 | **58s** (was >63 min — see §3) | **No — 72 failed, 9 errors, 1,911 passed** | **No** — `--collect-only` only |
| Frontend vitest | 136 | 713 | 35s | **No — 10-11 failing, flaky** | **No** |
| Playwright e2e | 18 specs | — | needs full stack | not run | **No** |
| MCP pytest | 15 | — | fast | — | **No** — import smoke only |

`.github/workflows/deploy.yml:81` is the only pytest invocation in CI:

```
-m pytest --collect-only -q
```

`--collect-only` imports test modules and exits without executing a single assertion.
It catches import errors. It does not guard behaviour. There is no vitest job, no
Playwright job, no lint job, no `tsc` job, and no coverage tooling anywhere
(no `pytest-cov`, no `.coveragerc`, no vitest `coverage` key, no codecov).

**Net: nothing in this repo is enforced at deploy time.**

## 2. Currently-failing frontend tests

Run 1: 5 files / 11 tests failed. Run 2: 4 files / 10 tests failed. **The suite is
non-deterministic** — that delta is flakiness, not a code change.

| Spec | Failing case |
|---|---|
| `user-management/settings/system-health/page.test.tsx` | 5 cases — threshold clamping, snake_case key persistence, recipient warning. Throws `TypeError: users?.map is not a function` |
| `user-management/account/components/notification-channels-preference.test.tsx` | 3 cases — PATCH on toggle, load prefs, revert on failure |
| `master-data-management/products/components/ProductsList.discontinued.test.tsx` | Discontinued vs Available pill rendering |
| `integration-management/integration-logs/components/IntegrationLogsList.test.tsx` | `created_from` active indicator in filter panel |

## 2b. Currently-failing backend tests (72 failed + 9 errors)

First complete run of this suite in an unknown length of time. The failures cluster tightly by
root cause, and the pattern is **schema and signature drift** — tests written against older
models that were never re-run as the code moved on. This is the direct cost of `--collect-only`
in CI: `collect-only` imports these files successfully, so nothing flagged them.

| Root cause | Count | Affected files |
|---|---|---|
| `TypeError: 'agent_id' is an invalid keyword argument for McpTool` | 14 | `test_mcp_access_service.py`, `test_access_agent_mcp_tool_service.py`, `test_access_agent_mcp_tools_routes.py`, `test_mcp_tools_picker.py`, `test_mcp_access_endpoint.py` |
| Pydantic `Field required` — `team_set_code`, `agent_code` missing | 12 | `test_conversation_sla_coverage_fanout.py`, `test_conversation_policy_binding.py` |
| `invalid input syntax for type uuid: "MSEG-A"` (code passed where UUID expected) | 10-12 | `test_market_segment_routing.py` |
| `sqlite3.OperationalError: unrecognized token: ":"` on `CREATE TABLE contact_access_types` | 8 | `_sqlite_compat.py` cast-stripping does not cover this table |
| `AssertionError: "This form is not escalated; the handling lock does not apply."` | 7 | `test_form_handling_lock_routes.py` |
| `no such table: form_sla_configs` | 4 | fixture table list incomplete |
| `no such table: conversation_sla_tracking` | 3 | fixture table list incomplete |
| `notify_spy.<locals>.<lambda>() got an unexpected keyword argument 'dedup_id'` | 4 | test double not updated after signature change |
| `Cannot escalate a resolved conversation SLA tracking.` | 4 | `test_sla_assignee_team_derivation.py`, `test_sla_due_escalations.py` |
| `async def functions are not natively supported` | 1 | `app/api/v1/test_auth.py` — a test file living under `app/`, missing asyncio config |

Failures by file (top): `test_market_segment_routing.py` (12), `test_form_handling_lock_routes.py` (7),
`test_conversation_sla_coverage_fanout.py` (6), `test_mcp_access_service.py` (5),
`test_ticket_intake.py` (4), `test_system_health_watchdog.py` (4), `test_rbac.py` (4 errors),
`test_list_column_preferences.py` (4 errors), `test_access_agent_mcp_tool_service.py` (4).

**Not yet triaged against production behaviour.** Most of these read as stale tests rather than
live bugs, but that is an inference from the error shapes, not a verified claim. Two deserve real
scrutiny before being dismissed:

- `test_market_segment_routing.py` — a market-segment **code** (`"MSEG-A"`) reaching a `uuid`
  column is the kind of contract mismatch that can be a genuine defect, not just a stale fixture.
- `test_form_handling_lock_routes.py` — the "not escalated" assertion touches the
  `escalated_at`-vs-`current_tier` distinction that has bitten this codebase before.

## 3. Why the backend suite took an hour — RESOLVED (81x)

Not test count, not Postgres, not lack of parallelism. A chain of three defects:

**1. `tests/conftest.py:81` — autouse fixture, runs after every single test:**

```python
_keys = list(_r.scan_iter(match="idemp:*", count=500))
```

Redis `SCAN MATCH` walks the **entire keyspace** server-side and filters. Cost scales with
total keys, not with matches. It found zero matches, every time.

**2. Dev Redis held 12,142,845 keys / 17.95 GB**, `maxmemory 0`, `maxmemory_policy noeviction`.
So every test paid a full 12M-key walk. Measured: a bare `redis-cli --scan --pattern "idemp:*"`
took **25.6s**.

**3. Root of the bloat — a producer with no consumer:**

```
rq:queue:embeddings  LLEN = 11,929,628
```

11.9M jobs backlogged on the `embeddings` queue, oldest sampled `created_at 2026-05-31T06:03:06Z`,
`status: queued`, `ttl: -1` (no expiry). Nothing consumes it:

- `worker.py:68` → `ForkSafeWorker(['imports', 'respond_io'])` — `embeddings` not listed
- `queue_service.py:23` → `_IMMEDIATE_DRAIN_QUEUES = {"notifications": 5}` — `embeddings` not listed

A separate DB-table path (`_run_embedding_db_queue_fallback` over the `embedding_queue` table
in `app/scheduler/task_scheduler.py`) appears to be the real consumer, which would make the
Redis enqueue a redundant producer nothing drains. Consistent with `embedding_service.py` and
`embedding_worker.py` having zero tests — nothing would have caught it.

### Measured impact of the fix

Local Redis purged with `FLUSHALL ASYNC` (verified 100% RQ keys beforehand — a 200k-key sample
contained zero non-RQ keys; `idemp:*` keys carry their own ≤60s TTL and need no manual sweep).

| Run | Before | After |
|---|---|---|
| 10-file subset (291 tests) | 907.28s | **11.23s** |
| Full suite (232 files, 1,991 tests) | >63 min (killed, never finished) | **58.09s** |

Subset results were **identical** before and after (1 failed / 290 passed both runs), so the
purge changed timing only, not outcomes. `pytest --durations` went from every top-15 slot being
`teardown` to the slowest entry being a 1.12s real-fixture Excel parse.

### Still outstanding

1. **The scan is still O(keyspace).** It will degrade again as RQ jobs accumulate. Fix
   `conftest.py:81` — point tests at a dedicated Redis logical DB and `FLUSHDB`, or have the
   idempotency middleware maintain a small index set, instead of a blind prefix scan.
2. **The embeddings producer/consumer mismatch is unfixed** — purging local Redis cleared the
   symptom, not the cause. It will refill.
3. **Prod Redis unverified.** If it leaks the same way, `noeviction` + unbounded growth ends in
   OOM-on-write. Read-only check:
   `docker compose exec redis redis-cli LLEN rq:queue:embeddings` (run twice, minutes apart —
   a rising number means an active leak). Do **not** `FLUSHALL` prod; that would destroy
   genuinely queued `imports` / `respond_io` jobs.
4. **`pytest-xdist` is now installed** but unused — at 58s serial it is no longer the priority.
   Markers (`fast` / `db` / `slow`) and diff-scoped selection remain worthwhile but are optional.

## 4. Backend coverage by domain

Clustered by test filename prefix (file count):

| Cluster | Files | Cluster | Files |
|---|---|---|---|
| lookup | 14 | order | 5 |
| ai / assistant | 14 | mcp | 5 |
| sla | 13 | list_query | 5 |
| complaint | 12 | ideation | 5 |
| promotion | 10 | coverage | 5 |
| form | 10 | stock | 4 |
| respond | 7 | record_context | 4 |
| email | 7 | product | 4 |
| attachment | 7 | team / pr / portal / integration / campaign / audit / access | 3 each |
| conversation | 6 | working_hours, whatsapp, variant, uuid, user | 2 each |

Largest single files: `test_sla_extend_deadline.py` (53 tests),
`test_complaint_do_fulfilment.py` (36), `test_sla_assignee_team_derivation.py` (32),
`test_respond_templates.py` (31), `test_form_handling_lock.py` (27),
`test_ai_prompt_registry.py` (27), `test_ai_extract_service.py` (27).

### Route domains — guarded vs not

| Domain | Route modules | Guarded | Gaps |
|---|---|---|---|
| `sla` | 5 | strong (~25 files) | — |
| `complaints` | 3 | strong (~15 files) | — |
| `lookup` | 1 | strong (~13 files) | — |
| `procurement` | 8 | good | `picking_lines.py` — 0 refs |
| `resources` | 4 | good | `attachment_types.py` thin |
| `master_data` | 10 | partial | `products_select.py`, `categories.py`, `units_of_measure.py`, `brands.py` |
| `order_management` | 4 | partial | `customers_select.py` |
| `user_management` | 14 | partial | `system_logs.py`, `permissions.py`, `quick_access.py`, `contact_impersonation.py` |
| `system` | 21 | partial | `numbering_rules.py`, `calendar.py`, `import_logs.py`, `jobs.py`, `references.py`, `outgoing_mails.py`, `mcp_routing.py`, `respond_workspaces.py`, `respond_outbox.py` |
| `marketing` | 5 | partial | `campaigns.py`/`campaign_types.py` thin, `promotion_products.py` |
| `public` | 5 | partial | `approval.py`, `ticket_drafts.py`, `view.py` |
| `notifications` | 2 | service-only | HTTP surface of `notifications.py` + `coverage.py` unguarded |
| `inventory` | 5 | **weak** | **`stock_ledger.py` — 0 refs. Stock movement correctness unguarded.** |
| `external` | 29 | **weak** | **~14 fully untested** — `rag.py`, `memory.py`, `view_link.py`, `work_calendar.py`, `conversation_variables.py`, `entity_attachments.py`, `complaint_attachments.py`, `product_attachments.py`, `it_support_tickets.py`, `ideation.py`, `respond_contacts.py`, `access_agent.py`, `spo_allocations.py`, `forms.py`. This is the n8n / API-key surface. |
| `activities` | 1 | **none** | 0 tests |
| `tickets` | 1 | **none** | only `test_ticket_intake.py`; e2e spec is the sole guard |
| `auth` | 1 | **none** | **login / signup / reset-password / change-password / verify-email all unguarded** |

### Services with zero tests (>=600 LOC)

| Service | LOC |
|---|---|
| `tickets_service.py` | 1,319 |
| `activities_service.py` | 791 |
| `embedding_service.py` | 770 |
| `attachment_notification_helper.py` | 685 |
| `embedding_worker.py` | 642 |

Under-tested for their size: `mcp_tool_capability_service.py` (2,577 LOC, 1 test),
`inventory_service.py` (1,936 LOC, 4 tests), `workflow_forms_service.py` (1,009 LOC, 1 test),
`entity_resolver.py` (3,951 LOC, 8 tests).

## 5. Frontend coverage

136 vitest files, overwhelmingly React render tests via `@testing-library/react` with
`@/lib/api` (`apiFetch`) mocked. Almost nothing tests routing, RSC/server-component
behaviour, or real network.

| Area | Test files |
|---|---|
| `components/` (top-level) | 20 |
| `resource-management` | 17 |
| `system-management` | 16 |
| `sla-management` | 14 |
| `user-management` | 12 |
| `master-data-management` | 10 |
| `procurement-management` | 9 |
| `lib/` | 8 |
| `portal` | 6 |
| `marketing-management` | 5 |
| `order-management` | 4 |
| `hooks/`, `integration-management`, `account` | 3 each |
| `services/` | 2 |
| `ideas`, `forms-management`, `complaint-management` | 1 each |

Ratios: `components/` ~13%, `hooks/` ~7%, `services/` ~14%, `lib/` ~18%,
`app/**` components ~8%. Data-fetching hooks — where API contract breaks surface first —
are the thinnest at ~7%.

## 6. Playwright e2e — the only true integration guards (18 specs)

These hit a real running app plus real backend. They are the only tests that would catch
an FE-to-BE contract break.

| Spec | Flow |
|---|---|
| `ai-bubble-record-context.spec.ts` | Ask AI about an open complaint; asserts `/assistant/record-context/complaint/` called and reply renders |
| `ai-prompt-registry.spec.ts` | Edit prompt, save version, publish moves production pointer |
| `complaint-master-data-and-notify.spec.ts` | Root Causes / Resolutions in sidebar; full CRUD of a root cause + notify |
| `complaint-print-count.spec.ts` | Print Count column, per-complaint downloads modal, Download PDF enqueues export |
| `complaint-record-navigation.spec.ts` | Filtered prev/next pager; total matches filtered list count |
| `contact-access-types.spec.ts` | Admin assigns access types to a contact; MCP-equivalent endpoint reflects new visibility |
| `documents-drive.spec.ts` | Unified Drive: sidebar to Files, root browse, breadcrumb root crumb |
| `impersonation.spec.ts` | Admin impersonates a non-admin user and exits |
| `portal-ai-extract.spec.ts` | Portal: drag docs, AI extract, review, confirm prefills complaint form |
| `portal-slug-links.spec.ts` | Public portal: no-session link-request card; unknown slug 404 |
| `product-field-attachments.spec.ts` | Upload tech-spec, link to product, field badges, AI Extract overwrites product |
| `request-batch-regressions.spec.ts` | Guards against connection-refused / stray `127.0.0.1:7242` requests |
| `sla-extend-deadline.spec.ts` | Extend on eligible pending-task row; new due date persisted |
| `stock-list-xlsm-upload.spec.ts` | Macro `.xlsm` stock upload converts to template-only `.xlsx` |
| `tickets.spec.ts` | Footer Support button to tickets; create + detail (TCK number, status pill, SLA strip) |
| `upload-activity-drawer.spec.ts` | Upload drawer empty state; single-file upload surfaces session + Integration tab |
| `user-guide-purchasing.spec.ts` | Validates purchasing user-guide claims against real UI |
| `whatsapp-templates.spec.ts` | Sync WhatsApp templates, set complaint default with param mapping |

## 7. MCP (`sorento_crm_mcp`)

3,967 LOC across 12 modules, 15 test files. Emphasis is heavily on output
sanitisation/redaction (7 of 15 files) — good against data leaks, weak on transport
and dispatch.

| Module | LOC | Tested |
|---|---|---|
| `server.py` | 1,559 | partial — bulk of tool registration/dispatch unguarded |
| `catalog.py` | 756 | yes |
| `presenters.py` | 595 | yes |
| `record_actions.py` | 192 | yes |
| `access_guard.py` | 98 | yes |
| `user_guides.py` | 234 | **no** |
| `escalation_hint.py` | 170 | **no** |
| `http_client.py` | 156 | **no** — retry/timeout/auth-header unguarded |
| `module_loader.py` | 103 | **no** |
| `settings.py` | 71 | **no** |

## 8. What the sqlite strategy structurally cannot catch

`tests/conftest.py` teaches sqlite to render `JSONB` and `ARRAY` as `JSON`, and
`tests/_sqlite_compat.py` strips any `server_default` containing a `::` Postgres cast
during DDL. Consequences — a test can pass while production breaks on:

1. **pgvector** — no `vector` type in sqlite. `embedding_service.py` + `embedding_worker.py` have zero tests anyway.
2. **`pg_trgm` trigram similarity** — `entity_resolver.py` depends on it.
3. **JSONB operators** — `->`, `->>`, `@>`, `?`, GIN containment behave differently or fail.
4. **Postgres ARRAY semantics** — `ANY()`, `&&`, `unnest()`; arrays are opaque JSON text.
5. **Server defaults with casts** — deliberately stripped, so `'[]'::jsonb` / `now()::timestamptz` insert-time behaviour never runs.
6. **Migrations** — schema comes from `create_all`, not Alembic. Model/migration drift ships silently. There is no migration test.
7. **Concurrency and row locks** — `StaticPool` is a single shared connection. `SELECT ... FOR UPDATE`, deadlocks, and the form-handling-lock contention path cannot surface.
8. **Constraints and triggers** — CHECK constraints, partial/expression indexes, FK `ON DELETE`.
9. **Type strictness** — sqlite accepts values Postgres rejects (the `conftest.py` comment about a leaked `"REAL_ADMIN"` audit actor failing only on live Postgres is a recorded instance).
10. **timestamptz arithmetic** — relevant to working-hours / SLA-clock code, where sqlite stores naive text.

## 9. Priority gaps, ranked

1. **CI executes zero tests.** Everything below is unenforced regardless of quality.
2. **Frontend suite is red and flaky.** 10-11 failures nobody sees.
3. **`auth.py` has no tests** — login, signup, password reset, email verification.
4. **Zero-test services with real business logic** — tickets, activities, embedding, embedding worker, attachment notifications.
5. **`app/api/v1/external/` — 29 modules, ~14 untested**, and it is the n8n / API-key surface with the highest blast radius.
6. **`inventory/stock_ledger.py` + `procurement/picking_lines.py`** — stock movement correctness unguarded.
7. **No Alembic migration test** — model/migration drift ships silently.
8. **Frontend `hooks/` at ~7%** — where API contract breaks land first.
