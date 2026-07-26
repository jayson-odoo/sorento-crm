# UAC — Configurable field-based CS routing (predicate engine)

**Status:** Draft (pre-code) · **Classification:** CORE · **Domain:** forms / procurement / sla
**Plan:** `documentation/plans/forms/PLAN-form-cs-routing-conditions.md`
**Contract:** the per-salesman CS pin (`respond_contact_cs_routing`, resolved in
`form_sla_service._resolve_pinned_assignee`, `:859`) gains a generic **match-conditions** predicate
set so a form routes to different CS PICs by any of the form's own field values. First concrete use:
Purchase Request routes by a new required `sales_type` field (`project` / `cash_sales`). The engine
is field-agnostic and applies to all use_cases.

Tags: `[BE]` backend · `[FE]` frontend · `[E2E]` playwright · `[T]` unit/service test.

Code anchors: pin table `RespondContactCsRouting` (`app/models/access.py:239`); resolver
`_resolve_pinned_assignee` (`app/services/form_sla_service.py:859`), `_PINNABLE_USE_CASES` (`:857`);
lookup system `app/models/lookup.py` (+ `LookupBinding` `:72`); sponsor_subject precedent
(migration `alembic/versions/243_sponsor_subject_lookup.py`, FE `PurchaseRequestForm.tsx:457-491`,
`LookupBoundField.tsx`, `LookupBoundLabel.tsx`).

---

## Group ST — `sales_type` field + lookup wiring

- **ST-1 `[BE][T]`** GIVEN the migration runs, THEN `purchase_requests.sales_type VARCHAR(50)` exists
  (nullable at DB level); lookup set `procurement_sales_type` exists with active options `project`
  (label "Project") + `cash_sales` (label "Cash Sales"); a `lookup_bindings` row binds
  `(purchase_requests, sales_type)` to that set; migration is idempotent and downgrades cleanly.
- **ST-2 `[BE]`** GIVEN a PR create request with `sales_type = 'project'`, WHEN it is submitted, THEN
  the row persists `sales_type='project'` (200/201).
- **ST-3 `[BE]`** GIVEN a PR create request **omitting** `sales_type`, WHEN submitted, THEN it is
  **rejected 422** (required at the PR form-schema level) — UNLESS the FE supplied the binding default
  (see ST-5). *(Required-ness is schema-level; the default makes it always satisfiable.)*
- **ST-4 `[BE]`** GIVEN a PR create with `sales_type='banana'`, WHEN submitted, THEN **422
  `invalid_lookup_value`** via the lookup write listener (`lookup_write_listener.py`).
- **ST-5 `[FE]`** GIVEN the PR create form opens fresh, WHEN it renders the `sales_type`
  `LookupBoundField`, THEN it is **pre-selected to `project`** (from `lookup_bindings.default_value`),
  and the field is a required Select.
- **ST-6 `[FE]`** GIVEN an **existing** PR is edited, WHEN the form opens, THEN the stored `sales_type`
  is shown and the default does NOT override it.
- **ST-7 `[FE][BE]`** GIVEN a **Sponsorship Form** create/edit, THEN there is **no** `sales_type`
  field on the SF form and SF persists `sales_type = NULL` (shared table, SF ignores it).
- **ST-8 `[BE]` (REGRESSION)** GIVEN pre-existing `purchase_requests` rows with `sales_type = NULL`,
  WHEN they are read / listed / edited, THEN no 422 (legacy NULL skips lookup validation) and they
  render with an empty `sales_type` (no crash, no UUID).
- **ST-9 `[FE]`** GIVEN a PR list/detail, WHEN `sales_type` is displayed, THEN it shows the option
  **label** ("Project"/"Cash Sales") via `LookupBoundLabel`, never the raw code or a UUID.

## Group DV — `lookup_bindings.default_value` (generic lookup feature)

- **DV-1 `[BE][T]`** GIVEN the migration, THEN `lookup_bindings.default_value VARCHAR` (nullable)
  exists; setting it to a value that is NOT an active option of the bound set is **rejected**.
- **DV-2 `[FE]`** GIVEN the lookup-sets admin binding UI, WHEN an admin edits a binding, THEN they can
  set/clear its `default_value` from the set's options.
- **DV-3 `[FE][T]` (REGRESSION)** GIVEN a binding with `default_value = NULL` (e.g. `sponsor_subject`),
  WHEN its `LookupBoundField` renders on a new form, THEN there is **no** forced pre-select (today's
  behaviour).
- **DV-4 `[BE]`** GIVEN `GET /api/v1/lookup/by-binding?table=...&column=...`, WHEN it returns, THEN the
  payload includes `default_value` (so the FE can pre-select) without breaking existing consumers.

## Group ME — predicate engine schema + matching (deterministic, test-FIRST)

- **ME-1 `[BE][T]`** GIVEN the migration, THEN `respond_contact_cs_routing.match_conditions JSONB NOT
  NULL DEFAULT '[]'` and `priority INT NOT NULL DEFAULT 0` exist; the old unique
  `(respond_contact_id, use_case)` is dropped and replaced by an expression-unique index on
  `(respond_contact_id, use_case, md5(canonical_json(match_conditions)))`; downgrade restores the
  2-col unique.
- **ME-2 `[T]`** a predicate `{field, operator, value}` with `operator='equals'` matches iff the
  form's `field` string-equals `value`.
- **ME-3 `[T]`** `operator='not_equals'` matches iff the form field != value (including when the field
  is present-and-different).
- **ME-4 `[T]`** `operator='contains'` (string field) matches iff `value` is a substring of the field;
  `not_contains` is its negation.
- **ME-5 `[T]`** a multi-predicate row (`[{sales_type,equals,project},{sponsor_subject,equals,showroom}]`)
  matches **only when BOTH** pass (AND); one failing predicate → the whole row is skipped.
- **ME-6 `[T]`** GIVEN a predicate `{sales_type, equals, project}` and a form with `sales_type = NULL`,
  THEN the predicate does **not** match (NULL field never equals a concrete value) → row skipped.
- **ME-7 `[T]`** an empty `match_conditions = []` row always matches (wildcard).
- **ME-8 `[T]`** predicates evaluate against the **form header row's own fields** only; a predicate
  naming a non-header/line-item field never matches (defensive) and is not offered in the UI.

## Group RES — resolution ordering (pure admin priority, test-FIRST)

- **RES-1 `[T]`** GIVEN two matching rows with `priority` 1 and 2 (same contact+use_case), THEN the
  **priority-1** row wins (lower first), regardless of predicate count.
- **RES-2 `[T]`** GIVEN a wildcard `[]` row at `priority=1` and a specific row at `priority=2`, both
  matching, THEN the **wildcard wins** (pure admin priority; confirms NO auto-specificity).
- **RES-3 `[T]`** GIVEN two matching rows at equal `priority`, THEN **`created_at ASC`** breaks the tie
  deterministically.
- **RES-4 `[T]`** GIVEN no row matches (or no rows exist) for the form, THEN resolution falls to the
  existing **round-robin** `get_next_assignee`, cursor semantics unchanged.
- **RES-5 `[T]` (REGRESSION, hard)** GIVEN existing routing rows migrated to `match_conditions=[]`,
  THEN resolution is **byte-identical to today** — the contact-wide pin still wins over round-robin
  for PR/SF.
- **RES-6 `[T]`** GIVEN a matched pin whose `cs_pic_user_id` is inactive OR not a tier-1 member of the
  resolved CS team, THEN it falls back to round-robin + `logger.warning`, never 500 (existing
  resilience preserved).
- **RES-7 `[T]`** the engine applies to **all** use_cases — a complaint routing row with predicates
  resolves by the same algorithm (even though none is configured today).
- **RES-8 `[BE]`** end-to-end: GIVEN contact C with rows `[{sales_type,equals,project}]→userA (prio 1)`
  and `[]→userB (prio 2)`, WHEN a PR from C with `sales_type=project` is **approved** and the CS stage
  spawns, THEN the tracker assignee is **userA**; a PR with `sales_type=cash_sales` → **userB**.

## Group CFG — config UI (predicate builder + ordering)

- **CFG-1 `[FE]`** GIVEN the CS-routing admin surface for a contact, THEN routes render as an
  **ordered/draggable list**; drag reorders `priority`; a new row appends last.
- **CFG-2 `[FE]`** GIVEN the predicate builder, THEN the **field** dropdown lists the form's
  user-facing fields (NOT `id`/`created_at`/`approved_by`/status/audit columns); the **operator**
  dropdown offers `equals`/`not_equals`/`contains`/`not_contains`, with `contains`/`not_contains`
  hidden for non-string (enum/numeric) fields; the **value** input adapts by type (lookup-bound field
  → option dropdown via `SearchableSelect`, string → text, number → number).
- **CFG-3 `[FE]`** GIVEN a route saved with predicates + priority, WHEN persisted, THEN a duplicate
  condition-set for the same `(contact, use_case)` is rejected (unique index; surfaced as a friendly
  error via `extractApiError`).
- **CFG-4 `[FE]`** GIVEN a wildcard `[]` row ordered ABOVE a more-specific row, THEN the UI shows a
  **non-blocking warning** (shadowing) but still allows save.
- **CFG-5 `[FE]`** dropdowns use `SearchableSelect`/`SearchableMultiSelect` (no raw `<select>`);
  destructive row-delete uses `ConfirmDeleteDialog` copy.

## Group E2E — round-trip

- **E2E-1 `[E2E]`** Navigate via sidebar to the contact CS-routing config; add a
  `sales_type equals project → userA` route + a wildcard `→ userB`; save; assert the `/api/v1/*` PUT
  carried the `match_conditions` + `priority`; then (fixture) approve a `project` PR from that contact
  and assert the CS tracker is assigned to userA.
- **E2E-2 `[E2E]`** On the PR create form, assert `sales_type` renders pre-selected to Project, is
  required (blocks submit when cleared), and persists on create (`browser_network_requests` shows the
  POST payload carrying `sales_type`).

---

## Test report skeleton (fill in Phase 2, key back to these ids)

| AC id | Layer | Test file / verification | Result |
|-------|-------|--------------------------|--------|
| ST-1,ST-8 | pytest | `tests/test_sales_type_lookup_migration.py` | ☐ |
| ST-2..ST-4 | pytest | `tests/test_pr_sales_type.py` | ☐ |
| ST-5..ST-7,ST-9 | vitest | `PurchaseRequestForm.test.tsx`, `LookupBoundLabel.test.tsx` | ☐ |
| DV-1,DV-4 | pytest | `tests/test_lookup_binding_default.py` | ☐ |
| DV-2,DV-3 | vitest | `BindingsSection.test.tsx`, `LookupBoundField.test.tsx` | ☐ |
| ME-1 | pytest | `tests/test_cs_routing_conditions_migration.py` | ☐ |
| ME-2..ME-8 | pytest | `tests/test_cs_routing_predicate_engine.py` | ☐ |
| RES-1..RES-7 | pytest | `tests/test_cs_routing_resolution.py` | ☐ |
| RES-8 | pytest | `tests/test_form_sla_cs_stage_routing.py` | ☐ |
| CFG-1..CFG-5 | vitest | `ContactCsRoutingTable.test.tsx`, `PredicateBuilder.test.tsx` | ☐ |
| E2E-1,E2E-2 | playwright | `e2e/form-cs-routing-conditions.spec.ts` | ☐ |
