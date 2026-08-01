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

---

## Group F1a - status on submission LINES, and a derived header

Required by the after-sales exchange/return flow (`REQUIREMENTS-inbox-2026-08-01.md` R1/R3): Customer Service
approves **some lines and rejects others**, each line carries its own **disposition**, and the submission's status
follows from its lines.

The whole risk of this slice is one thing: **a derived value that is also writable is two sources of truth.**
Most ACs below exist to stop that, not to add features.

### Line status

- **AC-F1a-1** `[BE][MIG]` Given `workflow_submission_lines` today carries only `line_group_id`, `sort_order` and
  `row_data`, Then it gains `status_id`, a `UUID(as_uuid=False)` FK to `statuses.id`, **nullable**. Nullable
  because line-level status is **opt-in per definition**: most forms have lines that are just data, and forcing a
  status on them would mean seeding a graph for every form that has a repeater.
- **AC-F1a-2** `[BE]` Given a new entity type, Then `workflow_submission_line` registers **FK-based**
  (`status_attr="status_id"`) per ADR-0013 rule 1, with its own default graph. It is **not** the submission's
  graph: a line's lifecycle is a per-item decision (approve, reject, substitute) and the header's is a case
  lifecycle. Sharing one graph would force every header state onto every line.
- **AC-F1a-3** `[BE]` Given a line belongs to a submission which belongs to a definition, Then its
  `scope_resolver` resolves the **definition** (one hop through the submission), so a definition forks its line
  graph exactly as it forks its header graph. This is the indirect case `scope_resolver` was designed for.
- **AC-F1a-4** `[BE]` Given a line transition, Then it is authorised by the engine and an out-of-graph move is
  **422**, identically to the header. One authority, not a second per-line rule engine.
- **AC-F1a-5** `[BE]` Given the fork-stranding defect (task #14: `fork_graph` does not remap records that already
  point at the default graph), Then line-level status must not ship until that is closed **or** a record-side
  guard raises `status_not_in_graph` when a line's current status is absent from its resolved graph. Lines
  multiply the exposure: one submission can strand many rows at once.

### Disposition

- **AC-F1a-6** `[BE][MIG]` Given a disposition is configurable master data and not a lifecycle, Then it is
  **NOT** a status and **NOT** a new master table. It reuses the existing lookup system: a `lookup_sets` row
  `workflow_submission_line_disposition`, its `lookup_options`, and a `lookup_bindings` row for
  `('workflow_submission_lines', 'disposition')`. The column is a `String` holding the option `value`, matching
  the seven existing bindings (`complaints.complaint_type` and friends). That buys the admin dropdown UI, the
  keyword search and the default-value behaviour for free.
- **AC-F1a-7** `[BE]` Given a disposition value, Then it is validated app-side against the **active** options of
  the bound set, exactly as the existing bindings are. An inactive or unknown value is rejected.
- **AC-F1a-8** `[DOC]` Disposition and line status are **orthogonal**. A line can be `approved` with disposition
  `exchange` or `credit_note`; rejecting a line does not imply a disposition. Do not collapse them into one
  column, and do not derive one from the other.

### The derived header - where the bugs live

- **AC-F1a-9** `[BE]` Given a definition opts into line-derived status, Then the header status is **computed from
  its lines and is not directly writable**. `apply_transition` on the header must refuse for such a definition,
  with a distinct error code. ADR-0013 rule 11 requires exactly one writer of a status column; a derived header
  that is also settable violates it and the two will disagree.
- **AC-F1a-10** `[BE]` Given derivation is **opt-in**, Then a definition that does not declare it keeps today's
  behaviour exactly: the header is set by transition and lines carry no status. No existing form changes shape.
- **AC-F1a-11** `[BE]` Given the recompute, Then it is **idempotent**: running it twice changes nothing, and
  running it on an unchanged submission performs no write and emits no transition log row. A derived value that
  logs on every recompute floods history.
- **AC-F1a-12** `[BE]` Given every non-cancelled line reaches a terminal status, Then the header moves to the
  definition's declared resolved status. **And given a line then leaves terminal, the header REOPENS.** The
  reopen case is not optional: `complaint_fulfilment_service` already implements exactly this shape (a
  `processed_by_cs` complaint becomes `fulfilled` when every non-cancelled linked DO is delivered, and reopens
  when one stops being delivered). Follow it, including that a cancelled line is excluded rather than counted as
  done.
- **AC-F1a-13** `[BE]` Given derivation reads the engine's **trait flags** (`is_terminal`, `is_archived`) rather
  than hardcoded status keys, Then a definition may rename or fork its line statuses without touching the
  derivation code. Branching on key strings here would re-create the coupling the status engine exists to remove.
- **AC-F1a-14** `[BE]` Given partial approval is the driving requirement, Then a submission with some lines
  approved and others rejected is a **first-class state**, not an error: the header reflects "decided" while the
  lines retain their individual outcomes, and nothing forces all lines to agree.
- **AC-F1a-15** `[BE]` Given a submission with **zero** lines, Then derivation must not claim "all lines
  terminal" and silently resolve it. An empty set satisfies "all" vacuously, which is the same class of bug as an
  empty `rules[]` matching everything (F0's trap). Zero lines means not derivable, and the header stays put.
- **AC-F1a-16** `[BE]` Given the header changes by derivation, Then the transition log records it with the
  derivation as the actor rather than attributing it to whoever last touched a line. A derived move has no human
  mover, and recording one is a lie in the audit trail.

### Boundaries

- **AC-F1a-17** `[BE]` Given reporting, Then it groups by status **key**, never id and never `category`, on lines
  as on headers. A forked line graph re-keys ids for the same rungs.
- **AC-F1a-18** `[BE][MIG]` Given migrations fork the head when more than one author writes them, Then F1a's
  migration is orchestrator-owned, chains onto `311_wf_submission_status`, and leaves exactly one head.
- **AC-F1a-19** `[BE]` Given no regression is acceptable, Then the full suite's failure set is **identical** to
  the pre-slice baseline, compared set-wise and not by count, run **serially** with `-p no:randomly`.
- **AC-F1a-20** `[FE]` F1a is backend-only. `workflow-forms-management` stays stale until F3, and the sidebar's
  app-wide `published-for-submission` call must keep working.

---

## Group F1a corrections - after the red suite exposed the gaps (2026-08-01)

The test author found ten problems while writing the suite. Six needed a decision rather than a wording fix.
Where these conflict with Group F1a above, **this section wins**. Originals stand for auditability.

### CORRECTION 1 - line decisions are silently destroyed by an answer edit (the serious one)

**Verified:** `update_submission` bulk-deletes every line and re-inserts with fresh UUIDs
(`workflow_forms_service.py:713-730`). Any edit that includes `lines` would therefore wipe every line status and
disposition, with no error. That is silent loss of exactly what this slice adds, and no AC covered it.

- **AC-F1a-21** `[BE]` Given any line of a submission has been **decided** (a status other than the graph's
  initial rung, or a non-null disposition), Then `update_submission` **refuses to replace lines**, with a distinct
  error code. A header-only edit (`lines is None`) stays allowed and is untouched by this rule.

  Refusing rather than merging is deliberate. A merge needs a stable per-row identity, and the document supplies
  none: `row_data` is free-form and the line `id` is server-generated, so any matching rule would be a heuristic
  that mis-attributes a decision to the wrong row. Losing a decision quietly is worse than refusing an edit
  loudly. A stable line key, and with it a real merge, is its own slice.

### CORRECTION 2 - a deriving submission could never be closed

AC-F1a-9 said `apply_transition` refuses for a deriving definition. Too broad: derivation only ever moves the
header between the two declared rungs, so a deriving submission could never reach any terminal state at all.

- **AC-F1a-22** `[BE]` Given a deriving definition, Then `apply_transition` refuses **only** moves into or out of
  the two declared derived rungs (`status_derived_not_writable`), and **permits** any other move. Derivation owns
  the open/resolved pair; the rest of the lifecycle stays human-driven, so a resolved submission can still be
  closed by hand. This keeps ADR-0013's one-writer rule scoped to the values that are actually derived, which is
  what the rule is for. **Supersedes AC-F1a-9.**

### CORRECTION 2b - gate on the TARGET only (third attempt at this rule)

Correction 2 fixed "a deriving submission can never be closed" by scoping the refusal to the derived pair. That
was still wrong, and only became visible once the routes existed and someone asked what a user could click.

The guard refused a move when **either** endpoint was in the pair. But AC-F1a-23 forces the open key to be the
graph's initial rung, so a deriving submission is **always created on a pair rung**, so `from` is always in the
pair, so **every manual move was refused**. `allowed-transitions` returned an empty list forever and a deriving
submission's detail page had no action buttons at all. The exact property pair-scoping was introduced to provide
was still not achieved.

- **AC-F1a-30** `[BE]` Given a deriving definition, Then a manual header move is refused **only when the TARGET
  is one of the two declared rungs** (`status_derived_not_writable`); moving **out** of the pair is permitted.
  Once the header is parked outside both rungs, `recompute_submission_status` declines to touch it, so permitting
  the move creates no second writer. Same shape as `complaint_fulfilment_service`, where `closed` and `rejected`
  are sticky and auto-fulfilment leaves them alone. **Supersedes AC-F1a-22, which supersedes AC-F1a-9.**

The lesson worth keeping: "refuse if either end is involved" reads as the safer choice and was the unusable one.
A guard on a derived value has to be asymmetric, because the whole point is that one direction is owned by the
machine and the other by a person. Also: the service-level test suite hid this by hand-parking the header, so
only an HTTP-level test with a real creation path exposed it. **A test that constructs the state it asserts on
cannot tell you whether that state is reachable.**

### CORRECTION 3 - the two declared rungs need validating, or a submission strands outside them

Both found by the test author, both otherwise silent:

- **AC-F1a-23** `[BE]` Given `apply_transition` refuses moves into the derived pair, Then
  `derived_open_status_key` **must be the header graph's initial rung** for that definition, validated when the
  definition is saved with a loud error. Otherwise a submission created on `draft` while the open key is
  `submitted` sits outside the declared pair forever, and derivation correctly refuses to hijack it, so the
  submission is permanently stuck with no way back.
- **AC-F1a-24** `[BE]` Given `update_submission` refuses to edit a submission whose header sits on a terminal
  status, Then `derived_resolved_status_key` **must NOT be terminal**, validated at save. A terminal resolved rung
  freezes the submission, and adding a line is the main reachable way to reopen one, so a terminal resolved rung
  makes reopen unreachable. Closing for good is a separate manual move, which AC-F1a-22 now permits.

### CORRECTION 4 - "a line leaves terminal" is not reachable through the line API

AC-F1a-12 assumed a line could be un-decided. It cannot: `approved` and `rejected` are terminal and
`assert_transition_allowed` refuses any move out of a terminal rung.

- **AC-F1a-25** `[BE]` Given reopen, Then the reachable triggers are: a line **added**, lines **replaced**, or an
  admin **clearing `is_terminal`** on a rung. Derivation's contract is to **notice** that the line population
  changed, not to be the path that changed it, so it must recompute correctly from whatever state it finds rather
  than assuming which API produced it. The reopen requirement in AC-F1a-12 stands; only its trigger list is
  corrected.

### CORRECTION 5 - disposition vocabulary, and the missing reason

AC-F1a-6's `exchange` / `credit_note` were illustrative and contradict `REQUIREMENTS-inbox-2026-08-01.md`.

- **AC-F1a-26** `[BE][MIG]` Seed R1/R3's actual vocabulary: `write_off`, `cn_cancellation`,
  `replacement_same_model`, `replacement_equivalent_value`, `replacement_wrong_model`, `repair`, `maintenance`,
  `nothing_to_collect`. It is admin-editable master data, so tests must not pin the list.
- **AC-F1a-27** `[BE][MIG]` Given R3's "nothing to collect" **requires a reason**, Then
  `workflow_submission_lines` also carries a nullable `disposition_reason`. Adding it now costs one column;
  discovering later that the requirement has nowhere to land costs a migration plus a UI change.
- **AC-F1a-28** `[DOC]` The line **status** `cancelled` and the **disposition** `cn_cancellation` are different
  things on different columns with near-identical labels. UI copy must keep them apart, and `cancelled` is the one
  derivation excludes.

### CORRECTION 6 - a derived move has no actor column to name

- **AC-F1a-29** `[BE]` Given the transition log's only actor column is `user_id`, an FK to `users.id`, a sentinel
  string is impossible. Then a derived move is marked by `user_id IS NULL` **and**
  `status_transition_id IS NULL` **and** `remark = DERIVED_TRANSITION_REMARK`. That satisfies AC-F1a-16 without
  adding DDL to the log table. An explicit `actor_kind` column is the better long-term shape and is deferred.

### Narrowed

- **AC-F1a-17 is narrowed to lines.** It said "on lines as on headers", but no header roll-up exists to mirror:
  `keys_by_entity` returns keys, not counts. Only the line-side count-by-key is in scope; a header roll-up is
  unbuilt on both sides and is not this slice's job.
- **AC-F1a-18 and AC-F1a-19 are gates, not tests.** A single alembic head and an identical failure set cannot be
  asserted from a test file. They are verified by the orchestrator, serially, with `-p no:randomly`.
- **F1a declares no HTTP surface.** Every AC is service-level, so the suite is service-level. If routes for line
  transition and disposition land here, endpoint tests (happy path, auth denial, 422) are a follow-up.

---

## Group F2 - the integration layer (SLA, portal, notifications, attachments)

The last forms-platform dependency before after-sales S1. Split into three buildable sub-groups because they
share nothing but the submission: **F2a** SLA, **F2b** portal, **F2c** attachments and notifications. Each can
land and be gated on its own.

Substrate note that shapes all three: a submission has **no `company_id`** (no `CompanyScopedMixin`), while the
multi-company work is landing elsewhere. Do not add one here on a guess.

### F2a - SLA reaches submissions

- **AC-F2a-1** `[BE]` Given `workflow_submission` is absent from the SLA machinery, Then it is added to
  **BOTH** definitions of the tuple: `FORM_SLA_TYPES` at `app/services/form_sla_service.py:32` **and** the
  duplicated literal `_FORM_SLA_TYPES` at `app/schemas/sla.py:559`, which drives a Pydantic validator at `:581`.
  **Adding it to only one passes the service and then 422s at the schema boundary.** A test must assert the two
  are equal, so the next person cannot half-add a type.
- **AC-F2a-2** `[BE]` Given the duplication is itself the defect, Then prefer making `app/schemas/sla.py` import
  the tuple rather than restate it, unless that creates an import cycle. If it does, keep both and pin equality
  with the test above, and say why in a comment.
- **AC-F2a-3** `[BE][MIG]` Given stage config lives in `form_sla_configs` keyed by
  `(source_entity_type, stage_code)` with `start_event` / `resolve_event`, Then at least one stage is seeded for
  `workflow_submission`, following the live shape (`complaint` uses `main`: submit -> approved,rejected, then
  `customer_service`: approved -> resolved).
- **AC-F2a-4** `[BE]` Given a stage is identified by `(source_entity_type, team_set_code)` and stages must not
  share a policy row, Then each seeded stage has its own, or the known duplicate-assignment bug returns: a
  shared policy plus an `_active_tracker` lookup that ignores `team_set_code` sends two "sla_assigned"
  WhatsApp messages for one form.
- **AC-F2a-5** `[BE]` Given a submission's status now moves by **derivation** as well as by hand (F1a), Then a
  derived move emits the SLA event the same as a manual one. Derivation is the only status writer for a
  deriving definition, so an SLA that only listens to `apply_transition` would never start or resolve a clock on
  exactly the forms after-sales needs.
- **AC-F2a-6** `[BE]` Given `advance_on_event` defaults to NULL meaning "any resolve advances", Then each seeded
  stage sets it explicitly to the approving event, or a rejection spawns the next stage. This is a known
  production defect in the existing configs, not a hypothetical.
- **AC-F2a-7** `[BE]` Given the handling lock, Then "escalated" is `escalated_at IS NOT NULL`, never
  `current_tier > 1`. A form can legitimately START above tier 1, so keying on tier falsely locks a
  never-escalated form and disables its CTAs.
- **AC-F2a-8** `[BE]` Given `conversation_sla_tracking` is shared by two systems discriminated only by
  `source_entity_type`, Then every contact-keyed conversation query keeps using `conversation_tracking_scope()`.
  Adding a sixth form type widens the set of rows a careless conversation query would falsely match.

### F2b - portal submission

- **AC-F2b-1** `[BE][MIG]` Given a submission may come from a contact rather than a user, Then it carries
  `respondent_contact_id` to `respond_contacts`, plus `source_entity_type` / `source_entity_id` so a submission
  can point back at whatever spawned it.
  **`respondent_contact_id` MUST be `String`, not `UUID`.** Verified: `respond_contacts.id` is a **TEXT** column
  (so is `portal_tokens.contact_id`), and a `uuid` column cannot hold a foreign key to a `text` one. Every
  existing FK into that table is a string for the same reason. This is the identical trap as `users.id`
  (AC-F1-16), and the instinct to match the other uuid FKs on `workflow_submissions` is what springs it.
- **AC-F2b-2** `[BE]` Given not every form is public, Then a **definition declares** whether it is
  portal-submittable and by which party kind. Default closed: a form is internal until someone says otherwise.
  This is the one place in the forms platform where fail-open would expose data.
- **AC-F2b-3** `[BE]` Given portal rows are created by `_instantiate`, Then `respond_inbox_url` is set **at row
  creation**. The admin chat panel renders empty otherwise, and it must be excluded from any
  `_editable_fields` payload application.
- **AC-F2b-4** `[BE]` Given `PortalToken.contact_id` stores the internal `respond_contacts.id`, Then any
  Respond.io inbox URL or message call resolves the contact's `respond_io_id` first. The two are not
  interchangeable and confusing them is a documented recurring bug.
- **AC-F2b-5** `[BE]` Given the portal already carries the four bespoke forms, Then a submission's portal
  surface reuses `PortalToken` + OTP rather than adding a second token scheme.

### F2b corrections - after the red suite (2026-08-01)

**AC-F2b-2 resolved: the gate is TWO columns, not one.** "By which party kind" does not survive contact with the
portal as a scalar. `PortalToken` carries only `contact_id` and `space_id`, so the only classification reachable
for the asker is a many-to-many (`contact_access_types`), and the match is a set **overlap**, not an equality.

- **AC-F2b-6** `[BE][MIG]` `portal_submittable` (boolean, NOT NULL, **server default false**) is the door;
  `portal_party_kinds` (jsonb, NOT NULL, default `[]`) is the narrowing, where empty means **no narrowing**.
  Deliberately not folded into one column: if "non-empty list = open" were the rule then "open to everyone" is
  unexpressible without a magic sentinel, and the natural empty-list reading flips to **fail-open on the exact
  column AC-F2b-2 warns about**. Both server defaults are load-bearing, since the columns are NOT NULL on a table
  that already has rows.
- **AC-F2b-7** `[OPS]` `contact_access_types` is admin-curated and most Respond.io-synced contacts have none, so
  a definition that declares kinds locks out every unclassified contact. That is correctly fail-closed, but it
  means a dealer-only form is an outage on day one unless dealers are classified first. **After-sales S1 owns
  that classification**; it is not a bug to be fixed by loosening the gate.

**AC-F2b-3's premise is false and is rewritten.** "Portal rows are created by `_instantiate`" is not true of a
workflow submission, and following it literally breaks the AC's own siblings. `_instantiate` is a per-kind
constructor over four flat-column models plus a setattr allow-list; a submission has JSONB answers validated
against a **published version**, plus `version_id` and a `status_id` resolved from the engine. Routing through it
means either skipping F0 validation and the publish gate, or duplicating `create_submission`.

- **AC-F2b-8** `[BE]` The portal path goes through `WorkflowFormsService.create_submission`, which gains
  keyword-only `respondent_contact_id` / `source_entity_type` / `source_entity_id` / `respond_inbox_url` and must
  accept `user_id=None`. That is what buys F0 validation, the publish gate, the version pin and the F2a
  `submission_created` emit **for free**. AC-F2b-3's real content is its two invariants, which stand:
  `respond_inbox_url` is non-null in the creating INSERT, and it is unwritable from a contact payload.
  Reuse `PortalService._build_respond_inbox_url` verbatim rather than reimplementing it; it already resolves
  `respond_io_id` and already returns None when the contact has none, which is the whole of AC-F2b-4.

- **AC-F2b-9** `[BE]` **A portal submit starts the same SLA clock an internal one does**, and the tracker carries
  `respond_contact_id`. F2a emits `submission_created` from `create_submission` and nowhere else, so a portal
  path that builds the row itself silently skips it, and the submissions with no deadline are then precisely the
  ones a customer filed. Nothing reports that: an SLA that was never started is indistinguishable from one nobody
  configured. The existing portal already learned this (`submit_draft` carries an explicit `emit_form_event`
  block commented "Portal submit bypasses the API state-transition methods"). A **refused** submit must start no
  clock, so the gate runs before the spawn.

- **AC-F2b-10** `[BE]` **F2a gap to close here:** `emit_submission_event` never passes `contact_id` to
  `emit_form_event`, which is what populates `conversation_sla_tracking.respond_contact_id` - the field the
  WhatsApp channel and the CS pin lookup both key on. Without it a portal submission spawns a tracker with a
  deadline and no way to reply to the person who filed it. Read `submission.respondent_contact_id` **inside** the
  emitter rather than adding a kwarg, so no caller can forget it.

- **AC-F2b-11** `[BE]` **A contact may edit only while the submission sits on its definition's initial rung.**
  F2b did not define portal editability at all. This needs no new column (the four bespoke forms use
  `portal_draft_at` plus a rejected-is-editable rule; a submission has a status graph instead, and
  `update_submission` already refuses a terminal status). Ownership is checked separately: another contact's
  submission is 403 or 404, never readable.

- **AC-F2b-12** `[BE]` **Portal routes live under `app/api/v1/public/portal.py` behind `get_portal_token`.**
  Placing them under `app/api/v1/workflow_forms/` inherits the JWT dependency, so no contact could ever reach
  them, which then invites exactly the second token scheme AC-F2b-5 forbids.

**Name collision, kept deliberately.** `source_entity_type` / `source_entity_id` here mean "what spawned this
form". On `conversation_sla_tracking` the same names mean the **form type** and the form's own id. Same schema,
opposite referents. Kept anyway, because ADR-0009 already establishes this pair as the repo's polymorphic
"what spawned this" idiom for `service_jobs`, so renaming here would make the after-sales code inconsistent with
its own ADR. `source_entity_id` is `String`, not uuid: a polymorphic pointer cannot assume every target has a
uuid PK, and `respond_contacts` and `users` are text.

### F2b corrections, round 2 - found at implementation (2026-08-01)

- **AC-F2b-13** `[BE]` **The submission serializer must split admin from portal.** `_submission_out` does not
  emit `respond_inbox_url`, and it was right not to: the portal's own `get_submission` uses the same serializer,
  so adding it would put an **admin inbox URL into the payload a customer reads back**. But the whole point of
  writing that URL at row creation is the admin chat panel, and the admin detail page reads this serializer, so
  as shipped the column is populated and nothing renders it. Two serializers, or one with an explicit
  `include_admin_fields` flag defaulting to **False**. Admin-only: `respond_inbox_url`, `respondent_contact_id`,
  `source_entity_type`, `source_entity_id`. Defaulting the flag to False is what makes a future caller's
  omission safe rather than leaky.
- **AC-F2b-14** `[BE]` **Validate declared party kinds against `contact_access_types` at save.**
  `update_definition` normalises case but does not check the codes exist, so typing `dealers` for `dealer`
  produces a form open to **nobody**, silently, and the symptom is indistinguishable from AC-F2b-7's "dealers are
  not classified yet". A `WHERE code IN (...)` check at save turns a silent outage into a validation error.
- **AC-F2b-15** `[BE][MIG]` **Portal editability needs a one-way latch, because "initial rung" is not
  monotonic.** AC-F2b-11 said a contact may edit while the submission sits on its definition's initial rung. For
  a **deriving** definition the initial rung IS the derived open key, and the header **returns** there whenever
  lines are un-decided - so a submission would become contact-editable again *after staff had started work on
  it*. Add `workflow_submissions.portal_locked_at` (nullable timestamp), stamped the first time the submission
  leaves its initial rung, and require `portal_locked_at IS NULL` **as well as** the initial rung. A latch is
  monotonic where a status test is not. **Supersedes AC-F2b-11.**
- **AC-F2b-16** `[BE]` `get_definition_schema(token, definition_id)` is accepted as a sixth portal method: the
  five pinned ones never let a contact render a form they have not already filed, since the schema only arrives
  on `get_submission`. Same `_assert_submittable` gate, then the published preview. Without it the route surface
  ships unusable.
- **Flagged, not fixed:** `PortalService._build_respond_inbox_url` returns None when
  `settings.respond_app_base_url` is unset, so on a deployment that never configured it every portal submission
  gets a NULL inbox URL, looking exactly like the bug AC-F2b-3 exists to prevent. Environment config, not code.

### F2c - attachments and notifications

- **AC-F2c-1** `[BE][MIG]` Given attachments, Then both **submission-level and line-level** linkage exist,
  reusing `attachments` and the existing `storage_router`. Line-level matters because the after-sales flow
  attaches proof per returned item, not per case.
- **AC-F2c-2** `[BE]` Given attachment keys, Then they are `{type}/{id}/{original_filename}`, never
  `{type}/{name}`, which collides across records. `original_filename` is the immutable upload name and the key
  basename; `stored_filename` is the editable display name.
- **AC-F2c-3** `[BE]` Given per-type caps, Then the cap is read from the configurable
  `attachment_types.max_count_per_entity`, with blank meaning unlimited. Do not hardcode a limit.
- **AC-F2c-4** `[BE]` Given `notifications.user_id` is **NOT NULL** (verified), Then a contact-facing
  notification cannot be written by putting a contact in `user_id`. Whatever path is chosen must be explicit
  about how a contact is addressed, and a test must cover a contact-only recipient. This is the constraint most
  likely to be discovered late.
- **AC-F2c-5** `[BE]` Given every Respond.io send must be auditable, Then a send writes an `integration_log`
  row on **success and failure**, mirroring `_send_and_log`. Local testing runs with intentionally wrong
  credentials, so a 401'd send must still appear in the outbox. `integration_log.business_id` is a UUID column:
  use the notification id, never a composite string.
- **AC-F2c-6** `[BE]` Given notification is a post-commit side effect, Then it is best-effort: catch and warn,
  never raise. Otherwise the caller gets a 500 for an operation that actually succeeded, and the retry takes an
  idempotent path that never backfills the missed side effect.
- **AC-F2c-7** `[BE]` Given SLA notify is a matrix, Then the stage boolean AND the per-user per-event toggle both
  gate a channel. In-app always sends when the stage allows; WhatsApp additionally needs a linked
  `RespondContact`.

### F2a corrections - after the red suite (2026-08-01)

Writing the suite produced ten findings. Six needed a decision. Where these conflict with F2a above, **this
section wins**.

**AC-F2a-2 resolved, preferred branch confirmed.** `app/schemas/sla.py` CAN import the tuple from
`form_sla_service` with no cycle (verified: importing the service never pulls in the schema module, and
`app/schemas/__init__.py` is a bare comment). So delete the literal and import it, and assert **identity** not
equality: equality would pass a second literal that merely agrees today.

- **AC-F2a-9** `[BE]` **A deriving definition has no reachable event to start a clock, so a creation event is
  required.** `assert_manual_header_move_allowed` refuses every manual move INTO the derived pair, and a
  submission is *created* on the open rung with no transition at all. So the only header events a deriving form
  can fire are the pair's two keys, and the resolved one fires when the work FINISHES. A stage could only start at
  the wrong end of the clock. Therefore: a distinct **`submission_created`** event is emitted when a submission is
  created, and a deriving definition's first stage starts there. Non-deriving forms keep starting on the
  status-move event, exactly as `complaint` starts on `submit`. Two event sources, chosen per definition, rather
  than overloading status with a meaning it does not have.
- **AC-F2a-10** `[BE][MIG]` **`form_sla_configs` must scope per definition.** `emit_event` selects every active
  config for the TYPE, and `workflow_submission` is one type for every definition, so one seeded chain would apply
  identically to an RMA form, a warranty claim and a satisfaction survey. Worse, `start_event` names status KEYS
  and keys are shared across forks by design, so a forked definition that renames a rung silently stops matching
  while one that reuses a key inherits another form's stage. Add a **nullable `form_sla_configs.definition_id`**
  (NULL = applies to every definition, so the five existing form types are untouched) plus one predicate in
  `emit_event`. After-sales needs several definitions with different stages; without this, F2a delivers a single
  global chain and S1 cannot use it.
- **AC-F2a-11** `[BE][MIG]` **Seed ONE stage, on the default vocabulary.** AC-F2a-3 said to follow the live
  two-stage complaint shape; that cannot be expressed here. The default submission graph's post-decision rungs
  (`approved`, `rejected`) are both terminal and nothing leaves a terminal rung, so there is no rung for a second
  stage to resolve on. Widening the default graph to create one is exactly what F1 refuses ("every real form is
  expected to fork", pinned by a test so widening is a conscious act). So: one stage on the default, and forked
  definitions add their own chained stages via AC-F2a-10. **Supersedes AC-F2a-3's two-stage instruction.** Note
  AC-F2a-4 is then vacuous against a single row, so its behavioural half must be tested on a two-stage chain the
  test builds itself.
- **AC-F2a-12** `[BE]` **The emit belongs in the service callers, post-commit, not inside
  `recompute_submission_status`.** That function documents "flushes, never commits", and `_start_for_config`
  calls `db.commit()` unconditionally, so an emit inside recompute would commit a caller's half-built
  transaction: `create_submission` recomputes BEFORE its own commit, so an SLA start would commit a partially
  built submission. `create_submission`, `update_submission(lines=...)` and `apply_line_transition` each compare
  the header status before and after and emit after committing, best-effort.
- **AC-F2a-13** `[BE]` **Every SLA notification for a submission currently links to a 404.** Four per-type lookup
  tables have no `workflow_submission` entry and each degrades silently: `_form_detail_link` falls through to
  `/workflow-submission/{id}`, which is not a real FE route; `_STAGE_ACTION_LABELS` degrades a precise escalation
  reason to "The assignee did not act on this form"; `_FE_RECORD_ROUTES` (and `MyPendingSLAWidget.ENTITY_ROUTES`,
  which its comment says must match) resolves a notification link to a Respond inbox instead of the record; and
  `_ENTITY_NUMBER_SOURCE` has no entry, so notifications name the type rather than a document. Fix the first
  three in F2a. `_ENTITY_NUMBER_SOURCE` cannot be fixed: `workflow_submissions` has no number column and
  numbering is explicitly ungrilled, so the type-name fallback stays, but as a recorded choice.
- **AC-F2a-14** `[BE]` `submission_status_event(status_key)` must be **injective** over the status keys: two keys
  mapping to one event name means one rung's move fires another rung's stage. Returning the key itself satisfies
  this and reads naturally in a seeded config.

Two flagged, deliberately NOT fixed here:

- **`resolved_by` is auto-stamped from the tracker's assignee**, so a derived resolve names a person rather than
  nobody, against the spirit of AC-F1a-29. Changing it affects all five existing form types, so F2a pins the
  weaker correct invariant instead: a derived resolve must not name whoever decided the *line*.
- **The reopen path stays unreachable** (task #17): no add-one-line endpoint, and `assert_lines_replaceable`
  refuses replacement once any line is decided, which is always true of a resolved submission. F2a inherits this;
  a stage configured to start on the open key can therefore never restart.

### Gates for all three

- **AC-F2-8** `[BE]` Full-suite failure set identical to the pre-slice baseline, compared set-wise, run
  **serially** with `-p no:randomly`, and **with the dev stack stopped** - a live backend on the same database
  produces hundreds of bogus failures (observed: 1002).
- **AC-F2-9** `[BE][MIG]` Migrations orchestrator-owned, chained onto `312_wf_line_status`, exactly one head,
  and written defensively since the shared dev database is stamped on another worktree's chain.

## Deferred, with the reason

- **F1a** (submission **lines** carry `status_id` + disposition, header status derived) is a separate slice.
  After-sales needs it; F1 does not deliver it.
- **F2** (SLA / portal / notifications / attachments) needs `workflow_submission` added to `FORM_SLA_TYPES`.
- **Revision chain** (`submission_group_id` / `revision_number` / `is_current`) stays **ungrilled**. It changes
  what "resubmit" means on the portal and how SLA clocks attach across revisions, so it is F2's problem at the
  earliest, not F1's.
- **Numbering** stays ungrilled: `document_numbering_rules` versus the shared service's numbering engine. Two
  systems must not both own form numbers.
