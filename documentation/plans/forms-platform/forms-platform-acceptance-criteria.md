# Forms platform - acceptance criteria

Companion to `PLAN-forms-platform.md`. Written 2026-08-01, before F1 code, per `PRINCIPLES.md`.
F0's criteria are recorded retrospectively because F0 shipped test-first against a contract pinned in the test
suite itself; they are listed so the gate is auditable, not to re-litigate them.

Substrate rule for every AC below: **Postgres only, never sqlite.** All five `workflow_*` tables hold **0 rows**,
so F0 to F2 reshape rather than migrate. That is the single fact that makes this slice cheap, and it expires the
moment a real definition is authored.

---

## Group F0 - the document model (SHIPPED, gated 2026-08-01)

- **AC-F0-1** `[BE]` Given `app/form_engine/{schemas,validation,computed}.py` ported from
  `foundryx-shared-service`, Then the field taxonomy covers composites, uploads, display-only, rating, repeater
  sub-fields, table columns and pages, and a document round-trips `model_dump(by_alias=True, exclude_none=True)`
  unchanged. **VERIFIED:** 347 tests.
- **AC-F0-2** `[BE]` Given computed expressions, Then a real tokeniser/parser/AST evaluates arithmetic,
  precedence, parens, unary minus and `SUM`/`AVG`/`COUNT`/`MIN`/`MAX` over repeater and table rows, with
  **no Python evaluation path** (`eval`/`exec`/`compile` absent). `parse_expression` raises;
  **`evaluate` never raises** and returns `None` for missing, null, non-numeric, bool, list/dict and
  divide-by-zero. **VERIFIED**, including a hostile-input test.
- **AC-F0-3** `[BE]` Given the publish gate `validate_form_doc`, Then it reports **every** problem rather than the
  first, and an unknown field type is a problem at **all three** levels (field, table column, repeater
  sub-field) - the source typed all three as bare `str`, so a document from a newer builder published clean and
  then silently dropped the field. **VERIFIED.**
- **AC-F0-4** `[BE]` Given the rule-engine node shape `{combinator, rules[]}` where an empty `rules[]` matches
  **everything**, Then an authored-but-empty condition group blocks publish AND matches **nothing** at runtime,
  and `is_visible()` is the only visibility call in the module so the trap cannot be re-inherited.
  **VERIFIED.**
- **AC-F0-5** `[BE]` Given a condition tree nested past `_MAX_DEPTH`, Then publish reports it rather than
  failing silently at runtime, and the boundary is pinned on **both** sides (5 deep publishes, 6 deep blocked).
  **VERIFIED.** Without this an author published clean and got a field that never appeared, with no explanation.
- **AC-F0-6** `[BE]` Given a `date` answer, Then only zero-padded `YYYY-MM-DD` is accepted; the source's bare
  `strptime` accepted `2026-6-1`, letting two spellings of one day into a JSONB map that is sorted and grouped
  as strings. **VERIFIED.**

---

## Group F1 - status lives on the submission, not in the schema

The premise: `workflow_submissions.current_state_code` is a `VARCHAR(64)` fed by a state machine embedded in
`workflow_form_versions.schema`. ADR-0001 puts the graph in the status engine, and after F0 there are **two**
validators describing that one JSONB column which disagree with each other. F1 ends that.

### The move itself

- **AC-F1-1** `[BE][MIG]` Given the adopted status engine, Then `workflow_submissions` carries
  **`status_id`** as a `UUID(as_uuid=False)` FK to `statuses.id`, NOT NULL, and `current_state_code` is
  **dropped**. No dual-write and no compatibility column: 0 rows means there is nothing to reconcile, and
  keeping both is how two sources of truth start.
- **AC-F1-2** `[BE]` Given `workflow_submission` is registered as a status-engine entity, Then it registers
  **FK-based natively** (`status_attr="status_id"`), unlike `complaint`, which needed a key-valued adapter only
  because its column predates the engine. A new table has no such excuse.
- **AC-F1-3** `[BE]` Given a form definition, Then its graph is resolved through
  **`scope_resolver = lambda submission: submission.definition_id`**, so each definition may fork its own graph
  copy-on-write while unforked definitions resolve the default. This is precisely what the engine's
  `scope_resolver` exists for, and it is what lets an exchange request and a service complaint hold different
  states on one engine.
- **AC-F1-4** `[BE]` Given the **default** `workflow_submission` graph, Then it is deliberately **minimal and
  generic** - a real form is expected to fork - and every real form's states arrive by forking, never by
  widening the default. A test asserts the default graph's key set so widening it is a conscious act.
- **AC-F1-5** `[BE]` Given a submission is created, Then its `status_id` resolves from the graph's initial
  status for that definition's scope, and a definition whose scope is unforked lands on the default's initial.
- **AC-F1-6** `[BE]` Given a transition request, Then it is authorised by the engine
  (`assert_transition_allowed`) and a move absent from the graph is **422**, whatever the client sends. The
  engine, not the schema document, is the authority.

### The audit trail

- **AC-F1-7** `[BE][MIG]` Given `workflow_submission_transition_logs`, Then `from_state_code` / `to_state_code`
  / `transition_id` become `from_status_id` / `to_status_id` / `status_transition_id`, all
  `UUID(as_uuid=False)` FKs (`from_status_id` nullable, for the first entry into the graph).
- **AC-F1-8** `[BE]` Given a log row, Then it is written on **every** accepted transition, and a transition
  that is rejected writes **nothing** - a rejected move is not history.

### Retiring the old shape

- **AC-F1-9** `[BE]` Given F0 landed a second validator, Then `workflow_forms_service`'s old-shape surface is
  **removed**, not left beside it: `validate_schema`, `default_draft_schema`, `validate_submission_payload`,
  `_state_id_to_code`, `_state_by_code`, `_initial_state_code`, `_header_fields_flat`, `_collect_field_defs`,
  `_validate_data_against_fields`, `_find_transition`, `_parse_iso_date`. Reads and writes of
  `workflow_form_versions.schema` go through `app.form_engine` alone. No release ships with both validators.
- **AC-F1-10** `[BE]` Given `tests/test_workflow_forms.py` pins the retired shape, Then it is **rewritten
  against the new one**, not deleted. Deleting the only test file for a 1,009-LOC service to make a slice go
  green is not a passing gate.
- **AC-F1-11** `[BE]` Given a definition's `draft_schema` default, Then it is a valid **`FormDocument`** (one
  page, one section, no states), replacing the old `default_draft_schema`'s embedded `s_draft`/`s_submitted`
  state machine.

### Role gating - narrowed on purpose

- **AC-F1-12** `[BE]` Given the old schema gated per state via `view_role_ids` / `edit_role_ids` on states and
  `allowed_role_ids` on transitions (all **default-open**: empty means allow), Then that behaviour is
  **preserved**, re-keyed from state ids to **status keys**, and transition permissions key by
  **`<from_key>:<to_key>`** rather than a transition id. Keys are stable across a scope fork where ids are not,
  which is the same reason reporting groups by key.
- **AC-F1-13** `[DOC]` Given "which permission system governs a form definition" is an **ungrilled** question
  (`PLAN-forms-platform.md`, Ungrilled), Then F1 does **not** answer it. Re-keying preserves today's behaviour
  and buys the decision time; it does not adopt the shared service's permissions engine, and it does not move
  gating into `user_role_permissions`. **Default-open must survive the move**: making it default-closed would
  silently lock every form.

### Boundaries

- **AC-F1-14** `[FE]` Given `workflow-forms-management` (builder, types, services, schema utils) is written
  against the retired shape, Then F1 **knowingly leaves it stale** and F3 rebuilds it. This is only acceptable
  because the feature has never run (0 definitions, 0 submissions), so no user can reach a broken screen. The
  blast radius is recorded rather than discovered later.
- **AC-F1-15** `[BE]` Given no regression is acceptable, Then the full suite's failure set is **identical** to
  the pre-slice baseline, compared set-wise and not by count. The gate runs **serially**: concurrent runs
  produce flaky mass failures on this shared database.
- **AC-F1-16** `[BE][MIG]` Given migrations fork the alembic head when more than one author writes them, Then
  F1's migration is orchestrator-owned, chains onto `310_seed_complaint_graph`, and `alembic heads` reports
  exactly one head. It also adds the `ForeignKey("users.id", ondelete="SET NULL")` missing from
  `created_by_user_id` / `updated_by_user_id` / `WorkflowSubmissionTransitionLog.user_id` (free at 0 rows;
  35 other columns already declare it). Those columns stay **`String`**: `users.id` is `Column(String)` and a
  `uuid` column cannot hold an FK to a `text` column.

---

---

## Group F1 corrections - after the blast-radius pass (2026-08-01)

A read-only impact map refuted two of the four premises this group was written on. The originals above stand as
written so the change is auditable; where they conflict, **this section wins**.

### REFUTED: "nothing outside the service and its router depends on the retired functions"

Three dependents, and the first two are on the **`app.main` boot import path**, so deleting the symbol is an
`ImportError` at `uvicorn` startup, before any route is served. Not a stale screen: a dead API.

```
app/main.py:24 -> app/api/v1/__init__.py:23,190 -> app/api/v1/list_query.py
  :25 -> app/services/workflow_submission_dynamic_list_query.py:22
            from app.services.workflow_forms_service import _collect_field_defs
  :23 -> app/services/list_query_search_service.py:12
            from app.services.workflow_forms_service import WorkflowFormsService
  :20 -> app/services/list_query_export_service.py:407,416
            reads WorkflowSubmission.current_state_code directly
```

- **AC-F1-9 is SUPERSEDED.** `_collect_field_defs` and `WorkflowFormsService` must **not** be deleted.
  `_collect_field_defs` must be **reimplemented against the `FormDocument` block shape**. It currently reads
  old-shape `header_sections` / `header_fields` / `line_groups`, so against a new-shape document it returns
  empty and **the dynamic `hdr:*` / `line:*` list-query columns silently go to zero**. Silent, not loud: no
  error, just an empty grid. This is a required F1 task, and it is the reason the function cannot simply go.
- **AC-F1-17** `[BE]` Given `list_query_search_service` calls `list_submissions(..., state_code=...)` and
  `list_query_export_service` filters on `current_state_code`, Then both are repointed to `status_id` / status
  **key**, and `workflow_submission_state_code` on `app/schemas/list_query.py:60-63, 97-99` is repointed too.
  The FE sends that filter key from two live call sites, so leaving it would 422 or silently ignore.

### REFUTED: "`workflow_form_versions.schema` and `draft_schema` are being retired"

They are **not**. F0 already stores its block document on those same two columns. What F1 retires is the
**state-machine keys inside the JSON** (`states`, `transitions`, `from_state_id`, `to_state_id`, and the
per-state role arrays) plus the **`current_state_code` column**.

- **AC-F1-18** `[BE]` Given F0's `tests/test_form_engine_schemas.py:1289` already persists `draft_schema=RICH_DOC`
  in the new shape, Then F1 must not touch those tests or those columns' existence. Treating the columns as
  retired breaks already-merged work.

### HALF-REFUTED: "0 rows, so nothing to backfill"

True of all five `workflow_*` tables (verified), and the FK graph is closed - no unnamed table references them.
**False of the module's config surface**, which F1 must migrate:

| table | rows | why it matters |
|---|---|---|
| `list_query_fields` | 14 | one row compiles to `sub.current_state_code` |
| `list_query_resources` | 2 | |
| `user_list_column_configs` | 4 | two keyed to definition UUIDs that no longer exist |
| `user_permissions` | 11 slugs | 5 role grants each |
| `tenant_modules` | 1 | `workflow_forms.enabled = true` |

- **AC-F1-19** `[BE][MIG]` Given `filter_compiler_adapters.py:147` resolves a field meta via
  `getattr(WorkflowSubmission, name)`, Then the persisted `list_query_fields` row pointing at
  `sub.current_state_code` is **deleted or repointed in the same migration that drops the column**. Otherwise
  every filter or export request including that field raises `AttributeError` at runtime, on a code-only deploy.

### CORRECTED: "the module has never run" and "leaving the FE stale is safe"

`PLAN-forms-platform.md` line 11 says the module has never run. Not true of **this database**: two
`user_list_column_configs` rows are keyed to definition UUIDs that no longer exist, so someone built and used
workflow forms here and the data was later purged. Row counts are 0; history is not.

The module is also **reachable and globally load-bearing**:

- `config/menu.config.tsx:643-654` is live in `MENU_SIDEBAR` (the compact twin at `:1503` is dead config,
  consumed only by demo6/demo10).
- `config/workflow-forms-dynamic-menu.ts` injects one sidebar child per published definition at runtime.
- **`demo1/components/sidebar-menu.tsx` calls `GET /workflow-forms/definitions/published-for-submission` on
  every page load in the entire app.** If that endpoint 404s, the global QueryCache `onError` toast fires on
  every page. A hazard comment at `sidebar-menu.tsx:99` already says so.

- **AC-F1-20** `[BE]` Given the sidebar depends on it app-wide, Then
  `/definitions/published-for-submission` keeps working across F1, in the same change. This is the one FE-facing
  endpoint F1 may not break.
- **AC-F1-14 is NARROWED.** "Knowingly stale" applies to the builder's state-machine UI (about 250 of
  `WorkflowFormBuilder.tsx`'s 769 lines) and the submission editor's transition controls. It does **not** license
  breaking the sidebar. FE blast radius: 21 files, 3,802 LOC - 6 hard break, 3 reshape, 12 unaffected.
- **AC-F1-21** `[FE]` Given `WorkflowSubmissionEditor.tsx:275-279` derives `terminal` from
  `schema.states[].is_terminal`, Then removing states must not leave `terminal` unconditionally `false`, which
  **enables Save on closed submissions** (`:348`, `:438`, `:444`). This is an authorization-shaped regression
  that throws nothing, so no test would catch it by accident. Derive terminality from the status graph's
  `is_terminal` instead.

### RESOLVED: AC-F1-22 was wrong to delete the table outright

AC-F1-22 below said delete `workflow_submission_transition_logs`. The implementer flagged the conflict rather
than silently picking a side: the spec suite imports the model and pins its shape and write behaviour in 8
tests, so deleting it fails the file at import.

**The AC was wrong, and it is the AC that changed.** Carrying the edge and remark on the submission instead
means `last_edge` / `last_remark` columns existing only to be diffed out of a JSONB audit row, for an entity
with one current status and many transitions. Worse shape, worse to query.

Resolution, now the worked example in ADR-0013 rule 11: **keep the table, narrowed to what `audit_logs` cannot
express** (`from_status_id` / `to_status_id` / `status_transition_id` / `remark`), **and** set `__audit_track__`
on `WorkflowSubmission` so the status diff itself lives in `audit_logs`. The table is never authoritative for
current status. The condition that keeps the two honest is that exactly one code path writes `status_id`;
verified, there are two writers and both are in the service (creation from the initial status, and
`apply_transition`). A direct write bypassing them is a defect.

AC-F1-22 as originally written is kept below for auditability.

### SUPERSEDED: one status trail, not two

- **AC-F1-22** `[BE][MIG]` Given `workflow_submission_transition_logs` calls itself "Audit trail of state
  changes" (`app/models/workflow_forms.py:153`) and holds 0 rows, and given `audit_logs` already captures every
  status change on an audited entity through the flush listeners, Then F1 **deletes that table** and sets
  `__audit_track__ = True` / `__audit_entity_type__ = "workflow_submission"` on `WorkflowSubmission`, following
  the `complaints` precedent (`app/models/complaints.py:16-18`). `audit_logs` brings actor, timestamp,
  trace_id, contact attribution and company scoping for free. **This supersedes AC-F1-7 and AC-F1-8.** If the
  edge taken and its remark must be retained, add columns to `workflow_submissions` and let the listener diff
  them - do not keep a parallel table.

### NEW: F1 flips role gating from fail-open to fail-closed

- **AC-F1-23** `[BE]` Given the retired gating fails open **twice over** (a missing state returns `True`, an
  empty role list returns `True`) while the status engine fails **closed** (an unknown key raises
  `status_not_in_graph`), Then this inversion is stated and intended, not incidental. Also verified:
  `_can_view_state` has **zero callers repo-wide**, so there is no view-level role gate today at all - only
  list-query permission slugs. F1 must not silently invent one.

### NEW: no forked-graph precedent exists

- **AC-F1-24** `[BE]` Given `SELECT count(*) FROM statuses WHERE scope_id IS NOT NULL` is **0**, and the only
  production registration (`complaint`) explicitly declares `scope_resolver = None`, Then AC-F1-3 makes
  `workflow_submission` the **first real consumer of `fork_graph`**. Budget for exercising copy-on-write
  end to end rather than copying a working example. `project` / `project_task` / `project_lead` are **not
  registered in this worktree** at all: their rows exist only because another worktree writes this shared
  database.

### NEW: pre-existing breakage to neutralise, not fix

- **AC-F1-25** `[MIG]` Given migration `108_seed_annual_dinner_sponsorship_workflow` resolves its seed at
  `docs/workflow-seeds/...` and `docs/` no longer exists (the `documentation/` rename), it already raises
  `RuntimeError` on any fresh database, and its guard only short-circuits when the definition already exists.
  Then F1 makes its `upgrade()` a **no-op** rather than fixing the path: the shape it seeds is the shape being
  deleted. Fixing the path would resurrect a dead document format.

### NEW: for F2, recorded now so it is not rediscovered

- **AC-F1-26** `[DOC]` `FORM_SLA_TYPES` is **duplicated**: the tuple at `app/services/form_sla_service.py:32-38`
  and a literal `_FORM_SLA_TYPES` at `app/schemas/sla.py:559` driving a Pydantic validator at `:578-585`. Adding
  `workflow_submission` to only one passes the service and then 422s at the schema boundary.

### Orphaned by F1, to handle deliberately

`email_event_registry.py:153-155` registers `workflow_form_state_transition` and
`notification_tasks.py:47` maps to it; the only producer is `workflow_forms_service._fire_notifications`
(`:863-974`), which reads `schema["notification_rules"]`. Retiring transitions orphans both. Also stale:
`mcp_tool_capability_service.py:1303` advertises a `state_code` filter for a tool the MCP server does not
register (MCP itself is clean - zero workflow references verified), and
`system-management/app-store/services/appModulesService.ts:173-182` duplicates the purge table list.

---

## Deferred, with the reason

- **F1a** (submission **lines** carry `status_id` + disposition, header status derived) is a separate slice.
  After-sales needs it; F1 does not deliver it.
- **F2** (SLA / portal / notifications / attachments) needs `workflow_submission` added to `FORM_SLA_TYPES`.
- **Revision chain** (`submission_group_id` / `revision_number` / `is_current`) stays **ungrilled**. It changes
  what "resubmit" means on the portal and how SLA clocks attach across revisions, so it is F2's problem at the
  earliest, not F1's.
- **Numbering** stays ungrilled: `document_numbering_rules` versus the shared service's numbering engine. Two
  systems must not both own form numbers.
