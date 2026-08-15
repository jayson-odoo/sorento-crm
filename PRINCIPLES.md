# PRINCIPLES.md — the non-negotiable contract (read FIRST)

The slim, always-true rules for Sorento CRM. **This file governs** — on conflict with
`CLAUDE.md`, this wins. `CLAUDE.md` is the detailed per-engine reference; `LESSONS-LEARNT.md`
is the running gotcha log; deep design detail lives in `documentation/`. Keep this file short.

> **What this is.** Sorento CRM — a live, single-tenant-stubbed FastAPI + Next.js CRM
> (orders, inventory, procurement, complaints, SLA, forms, resources, AI assistant, n8n +
> Respond.io WhatsApp integrations). Multi-tenant is stubbed (`DEFAULT_TENANT_ID`).
> The methodology below is fused from Sorento's three-phase loop and the FoundryX
> shared-service governance model.

## Methodology (mandatory order, every non-trivial feature)

**Run it with `/feature`** (`.claude/skills/feature/SKILL.md`) — it executes this order and
calls the `mattpocock-skills` plugin at the slots below. Two rules override that plugin:
**(a) files are the source of truth, tickets are the queue** — the UAC + PLAN files under
`documentation/plans/` are the contract, and `to-spec` must write there rather than publish
a spec issue; **(b) frontend mock before any backend code** — `implement` has no concept of
Phase 1, so scope it to Phase 2 only. Every step also has a **named executor** (main session
vs a `.claude/agents` subagent) - see the /feature skill map. Planning and grilling stay in
the main session; implementation (Phases 1-2) is delegated to the `coder` agent in a worktree;
review runs `reviewer` + `/code-review`, optionally `/codex-review` for a cross-model second
opinion. Running a step in the wrong seat is a process violation.

0. **Guided user experience FIRST — design the journey before the system.** Before any entity,
   table, endpoint or status graph is discussed, write the **guided journey**: who the actor is,
   what they see on the very first screen, what the system already knows (so they are never asked
   for it), each step in order, and what they hold at the end. Optimise for the **fewest decisions
   the user must make**, not for data completeness — the system infers, matches and pre-fills; the
   user confirms. Every field the design asks for must be justified against the journey, and
   anything derivable (from a receipt, a phone number, an order, a policy) is **derived, never
   asked**. The data model is then designed **backwards from that journey**. A plan that opens with
   a schema is a process violation. The journey goes at the top of the UAC file as its `Journey`
   section, and every AC traces to a step in it.
1. **Grill → UAC → plan.** Every piece of work starts with a grilling session (frontend
   AND backend) that resolves the full decision tree — **`/grill-with-docs`** when the work
   touches domain language or needs an ADR (it challenges the design against `CONTEXT-MAP.md`
   and writes ADRs into `documentation/adr/` inline), plain **`/grill-me`** for a pure UX or
   flow question. Module-sized work charts its unknowns with **`/wayfinder`** first. Then
   **write the User Acceptance Criteria
   FIRST** — `documentation/plans/<domain>/<slug>-acceptance-criteria.md`, the independently-
   verifiable Given/When/Then list (per-AC id, grouped by phase, tagged `[BE]`/`[FE]`/`[E2E]`/`[T]`).
   UAC is the contract. **THEN** write the plan (`documentation/plans/<domain>/PLAN-<slug>.md`)
   as the design that *fulfils* the UAC. **No plan ships without its UAC file.** `/to-spec`
   may draft both, but its output goes to those two files — it must NOT publish the spec as an
   issue. Render the plan with `/lavish` for review, then grill the plan itself before coding.
   Slice it with `/to-tickets` (tracer-bullet vertical slices, blocking edges) into GitHub
   Issues whose bodies link back to the PLAN and UAC paths; the files stay the contract and an
   issue that contradicts the UAC loses. Defer-items go to `documentation/backlogs/backlog.md`.
2. **Component-library discipline** — reuse first; a new variant = add a prop/mode to the shared
   component, never a parallel one-off. (`extractApiError`, `buildDataGridParams`,
   `userSelectService`, `ConfirmDeleteDialog`, `DataGrid`, mutation-hook factories.)
3. **Phase 1 — Frontend-first (mock).** UI → hook → service → **mock**. Tune every state
   (loading / empty / error / partial / success) with no backend running. Verify in a real
   browser (agent-browser headless, sidebar-click nav). Document the expected API contract. NO tests yet
   (shape may still shift), NO backend code. When the open question is "which of these designs",
   run `/prototype` BEFORE this phase and throw the result away — it is not built to the layering
   rules below and must never become the shipped FE.
4. **Phase 2 — Backend wiring, TDD.** Build BE (models → migration → schema → service → route)
   to match the Phase-1 contract, then swap the mock for the real `api-client` call (one-line at
   the service boundary). **This phase is test-FIRST (red → green → refactor), not test-after:**
   for every unit of behaviour, write the failing test BEFORE the implementation, watch it fail
   for the right reason, implement the minimum to pass, then refactor green. Applies to all
   backend logic — pytest (every route: happy + auth-denial + validation; every service branch)
   and, above all, **deterministic engines** (e.g. the SCM reorder maths): the golden-set expected
   numbers are written as failing tests first, and the code is built to satisfy them. FE hook/logic
   tests (vitest) are likewise test-first; FE component-state tests may follow once the prototype
   shape settles. One Playwright E2E per user flow (real clicks, FE→BE→DB). Tests are **never
   deferred** to Phase 3. Re-verify live. `/tdd` drives the loop; `/implement` may drive a whole
   ticket **at this phase only** (it calls `/tdd` internally and knows nothing of Phase 1).
5. **Phase 3 — Code review.** `/code-review` (or `ultra` for big diffs) → address via `--fix` /
   `/simplify` → open PR. Reviewer runs `documentation/reference/PR-CHECKLIST.md` + the DoD gate below.
   Use THIS repo's `/code-review`, not the plugin's same-named skill, unless asked otherwise.
   Inbound bugs enter via `/triage` (labels in `documentation/agents/triage-labels.md`) and are
   worked with `/diagnosing-bugs`; `/improve-codebase-architecture` and `/codebase-design` are
   periodic, never part of the feature loop.
6. **Branch** per feature; merge only after review. The user codes concurrently in the main
   checkout — `git status` before ANY branch/commit op; never assume the tree is clean.

## Modular architecture — classify core vs module FIRST (before UAC)

Every new feature/entity starts with one decision, recorded in the plan's header: **is this CORE or
a MODULE?**

- **CORE** = a **core system function** — a base-platform capability every install needs (auth,
  users, products, categories, stock, warehouses, suppliers, orders, the procurement base). Always
  present, not toggleable.
- **MODULE** = a **reusable, installable capability a customer/tenant turns on** — Sorento today,
  another customer (e.g. Rigel) tomorrow can just install the same module. Examples: the SCM
  reorder co-pilot, complaints, a ticketing add-on. The reuse axis is **across customers/tenants**,
  and it has **nothing to do with a "FoundryX shared service."**

**What makes something a module = enablement, not schema.** A module is defined by being
App-Store-installable per tenant: an `app_modules_catalog` entry + `tenant_modules` enablement +
the `require_module_enabled_with_api_key("<key>")` route guard, with declared dependencies in
`MODULE_MANIFEST`. That is the whole definition.

**Schema location is an independent decision.** A module does NOT have to own a separate Postgres
schema, and a separate schema does NOT require dropping FKs:

- **Default: `public` with normal FKs.** A module that extends the core domain (references
  `products`/`suppliers`/`stock`) lives in `public` and uses normal FKs — expected and correct.
- **Optional: a dedicated schema (`<module>.*`, e.g. `scm.*`) with normal cross-schema FKs.** Choose
  this for namespace clarity and clean uninstall (drop the schema, core records untouched). Postgres
  supports cross-schema FKs natively — **use them**; do NOT drop to id-value-only. Split by the
  **uninstall test**: durable business records that must survive the module being turned off stay in
  `public`; the module's own artifacts (policies, recommendations, computed scores, signals) go in
  the module schema. Migration does `op.execute("CREATE SCHEMA IF NOT EXISTS <module>")`; models pin
  `__table_args__={"schema":"<module>"}`.
- **Rare: an isolated schema with NO cross-schema FK** (id-value-only, service-layer integrity) —
  ONLY when the module genuinely must be liftable into its own database/service later. This is the
  exception, not the rule. Don't impose it by default.

**When unsure, default to CORE + `public`.** Promote to a module (installable) when a second customer
would genuinely install it; reach for a dedicated schema only for namespace/uninstall clarity, and
for FK-less isolation only when true DB-liftability is a real requirement. Don't pre-abstract.

Source-decoupling (e.g. a future AutoCount ETL swapping in beneath the reads) is achieved with
**read-model views** + `source_system`/`source_ref` columns — NOT by a separate schema.

The is_core flag in `app_modules_catalog` is about **App-Store enablement** (can a tenant toggle it),
the same axis as the module decision — not a separate schema axis.

## Definition of Done gate (a slice is NOT done until all pass)

1. **Mock swapped to real** + verified showing real data. A Phase-1 in-memory `*-service` is
   DEBT, not done — tag it loudly + backlog it.
2. **Backfill existing rows** — a new column/engine on an entity that already has rows needs a
   backfill migration, not just seed-if-absent. Idempotent JOIN-based "set where mismatch" beats
   "update where NULL" (fixes prior bad runs too).
3. **New permission → grant sweep** for already-provisioned roles/tenants, or the feature
   silently 403s / hides.
4. **New DB column reaches the FE** — add it to BOTH manual dict builders where they exist
   (`get_user`/`get_me`, `system_settings` GET dict + `*Update`); schema inheritance alone drops it.
5. **Verify from the USER's perspective** — real sidebar clicks, real data, at **375px AND 1280px**.
   Tests green ≠ user-verifiable. **`npm run dev` (HMR) for internal/team development; `npm run build
   && npm start` (prod) for EVERY handoff to the user** — never ask the user to test a dev server.
   The prod build matches their test env and surfaces build-only errors dev hides. Don't rebuild on
   every edit while iterating — that's the slow path; do rebuild before handing off or opening a PR.

## Design mandates (non-negotiable)

- **CRUD standard** (`documentation/reference/ADR-PRODUCT-STANDARDS.md`): list = DataGrid + search/filters +
  Add; create/edit = **modal by default** (dedicated page only for complex/multi-tab/file flows);
  view = dedicated `/{module}/{id}` detail page rendering **every section** with an explicit empty
  state + next-step CTA (never hide a section on missing data).
- **Delete = hard delete + confirmation.** Never `confirm()`; use `AlertDialog` /
  `ConfirmDeleteDialog`. Bulk-delete copy includes the count. Backend `DELETE` is hard; a
  soft-delete endpoint is **Archive**, never named "delete".
- **Confirm before every destructive OR detach action** — including Unlink, not just delete. Never
  one-click.
- **View and Edit are the SAME layout.** Same tabs in the same order, same fields in the same order
  within each tab; editing swaps a read-only value for an input **in place**. Nothing moves,
  appears or disappears between the two views. The read view is what teaches the user where things
  are, so if Edit reshuffles them every edit starts with re-finding the field, and a value that was
  visible but is now missing reads as data loss. Group a record's concerns into **tabs once** and
  reuse that tab set on both views. Read-only metadata (Created, Last Updated, ids) goes in the
  page header or a meta strip, **never inside a tab body**, because it has no edit counterpart and
  would otherwise force the two views to differ.
- **Detail pages carry prev/next record navigation** (`components/common/RecordNavigation`).
  Reviewing records one by one is the normal case; sending the user back to the list between each
  is what makes a screen feel half-built. Established usage: `user-management/users/[id]`,
  `order-management/customers`.
- **An optional select MUST be clearable.** `SearchableSelect` takes `clearable` — set it on every
  non-required select, or the user can change the value but never unset it.
- **Responsive** — every surface usable + non-clipped at 375px AND 1280px. Detail headers use
  `flex flex-col gap-3 sm:flex-row ...` (plain `justify-between` overlaps on mobile); modals are
  scrollable (`max-h` + `overflow`) so the submit button is reachable at phone width.
- **No UUIDs in the UI** — resolve to human-readable identifiers.
- **No feature explanations inside the UI** — put how-to in the Outline user guides / FAQ.
- **Datetimes** stored naive UTC; the MCP emits **naive Malaysia wall-clock** (not offset-aware);
  the FE renders via `formatDateTimeInMalaysia(rawString)`, never `formatDateTime(new Date())`.
- **Tests run on Postgres ONLY, NEVER sqlite.** No `create_engine("sqlite:///:memory:")`, no
  `@compiles(..., "sqlite")` shims, no mutating shared `Base.metadata` column types. sqlite's type
  affinity silently coerces UUIDs to ints and its constraint enforcement differs, so a sqlite test
  proves nothing about production and pollutes the shared metadata for later tests. Use the shared
  Postgres helpers in `tests/_pg_fixture.py` (`blank_session` for an isolated blank schema, or
  `SessionLocal` inside a rolled-back transaction). Seed real FK targets — Postgres enforces the
  constraints sqlite ignored.
- **NEVER use em-dashes in any writing**: not the em-dash character, not the en-dash, anywhere
  (code comments, commit messages, PR bodies, docs, chat). Use a plain hyphen with spaces, a comma,
  a colon, or parentheses instead.

## Layering (enforced)

- **Frontend:** UI component → hook (`useXxxQuery`/`useXxxMutations`) → feature service
  (`services/xxxService.ts`) → `lib/api-client` → FastAPI. Components NEVER call fetch/axios
  directly. Use `extractApiError` + `buildDataGridParams` (never hand-rolled). `apiFetch('/api/<domain>/...')`
  maps straight to backend `/api/v1/<domain>/...` (bypasses Next route.ts proxies).
- **Backend:** Router (HTTP/Pydantic only) → Service (business logic) → SQLAlchemy. Auth via
  `Depends`. Raise `AppException` (global handler serializes it). Post-commit side effects are
  best-effort (catch + warn, never raise — the retry takes the idempotent path).

## Code-review hard-fail rules (auto-reject)

Raw SQL / DB query in a router · a React component calling axios/fetch directly · duplicated
`extractApiError`/`buildDataGridParams`/user-select · a delete without a confirmation dialog · a
soft-delete named "delete" · a hidden empty section on a detail page · a hand-rolled
`<table className="table-fixed">` (use shared `DataGrid`) · a "done" slice still serving a mock ·
a new column/engine with no backfill for existing rows · a new permission with no existing-role
grant path · a new DB column missing from a manual dict builder · a write to `spec.values` /
`spec.provenance` / `spec.rendered_text` outside `app/services/product_spec_write.py` · a
non-searchable dropdown —
`@/components/ui/select`, raw `<select>`, or a hand-rolled `CommandInput` picker (every
dropdown-select MUST use `SearchableSelect`/`SearchableMultiSelect` from `@/components/common`; see
`ADR-PRODUCT-STANDARDS.md`).

## Ops quick-reference

- Local ports: backend **8000**, frontend **3000**, MCP **8765**. **FE: `npm run dev` (HMR) for
  internal/team dev; `npm run build && npm start` (prod) for EVERY handoff to the user** (never hand
  off a dev server — prod matches their env + catches build-only errors). Don't rebuild every edit
  while iterating — that's the slow path. Worker has **no reload** — restart after editing
  `app/tasks/*`; imports/Respond sends run ONLY on the worker (`OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` mandatory on macOS).
- Local DB (`DATABASE_URL` → `localhost:5432/sorento_ai_automation`) is a **copy of prod data** —
  safe to migrate/test; real prod migration is a separate deploy.
- Deploy: `DEPLOY.md` (blue/green via CI + `scripts/blue_green_deploy.sh`). Prod server
  `/opt/sorento-crm2/` has **no git repo** — CI scp's the deploy script; compose is edited by hand.
- New Alembic `down_revision` must chain onto a **committed** main head (not an uncommitted WIP
  migration); revision ids ≤ 32 chars. A branch merge forks two heads → fix with `alembic merge`.
