# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo layout

Monorepo. Four siblings:

- `sorento_crm_frontend/` — Next.js 15, React 19, Tailwind 4, Prisma (NextAuth + user/session DB only), Metronic 9 + ReUI shell. Calls FastAPI for all business logic.
- `sorento_crm_backend/` — FastAPI + SQLAlchemy + Alembic. All `/api/v1/*` business logic, RBAC, RQ workers, embedding pipeline.
- `sorento_crm_mcp/` — Read-only Streamable HTTP MCP server. Wraps backend GETs as MCP tools for n8n.
- `sorento_crm/` — Top-level `docker-compose.yml` + `deploy.sh` for the full stack.

Shared docs live in `docs/`. Treat `docs/ADR-PRODUCT-STANDARDS.md` and `docs/ARCHITECTURE-RULES.md` as binding.

**Plans:** every implementation/design plan (from planning sessions, grill-me, etc.) is written to `docs/plans/PLAN-<slug>.md` before implementation starts. Update the plan's Status line as work progresses.

## Common commands

### Backend (`sorento_crm_backend/`)

```bash
# venv + deps
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# migrate
alembic upgrade head
alembic revision --autogenerate -m "msg"
alembic downgrade -1

# dev server (root has main.py shim re-exporting app.main:app)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# or: ./run.sh

# RQ worker (imports queue) — needs REDIS_URL
python worker.py

# tests
pytest                                 # all
pytest tests/test_rbac.py -q           # one file
pytest tests/test_rbac.py::test_x      # one test
```

Pyright: root `pyrightconfig.json` points to `sorento_crm_backend/venv` and Python 3.12.

### Frontend (`sorento_crm_frontend/`)

```bash
npm install --force          # React 19 peer-dep conflicts; --force is expected
npm run build                # production
npm start        # copies .env.staging -> .env.local first
npm run lint                 # eslint .
npm run test                 # vitest run
npm run test:watch
npm run test:e2e             # playwright (e2e/, chromium, baseURL :3000)
npm run format               # prettier --write .
npm run format:check         # prettier --check . (currently red: 1743 files predate the config, see BL-008)

npx prisma db push           # apply schema
npx prisma generate          # regenerate client
node prisma/seed.js          # seed (also: npm run prisma:seed via "prisma":{"seed"})
```

Vitest: jsdom env, `@/` aliases repo root. Single test: `npx vitest run path/to/file.test.ts`.

### MCP server (`sorento_crm_mcp/`)

```bash
pip install -e ".[dev]"
export CRM_BASE_URL=http://localhost:8000 EXTERNAL_API_KEY=...
python -m sorento_crm_mcp        # default :8765/mcp
pytest                            # tests/
```

### Full stack via Docker

```bash
docker compose up -d            # from sorento_crm/ (root compose at sorento_crm/docker-compose.yml)
```

## Dev sessions (Claude-managed)

For any development task, Claude boots and owns the local stack as **background Bash sessions** so the user can test immediately. Boot all four at session start (or on first dev task):

| Service  | Command (run from its own dir)                                                                 | Port | Reload behavior |
|----------|------------------------------------------------------------------------------------------------|------|-----------------|
| Backend  | `venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` (in `sorento_crm_backend/`) | 8000 | `--reload` — backend file edits auto-restart uvicorn; nothing to do |
| Worker   | `PGGSSENCMODE=disable OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES venv/bin/python worker.py` (in `sorento_crm_backend/`) | —    | **No reload.** Restart manually after editing any RQ task (`app/tasks/*`). |
| Frontend | `npm run dev` (in `sorento_crm_frontend/`)                                                      | 3000 | **HMR — edits hot-reload; no rebuild.** Keep ONE persistent `npm run dev` server; do NOT kill/rebuild it to see a change. Use `npm run build && npm start` ONLY for handoff / final verify (see "Frontend dev loop"). |
| MCP      | `CRM_BASE_URL=http://localhost:8000 EXTERNAL_API_KEY=<from backend .env> backend venv's python -m sorento_crm_mcp` (in `sorento_crm_mcp/`; package installed in the backend venv) | 8765 | Restart manually after MCP code/catalog changes |

- Run each as `run_in_background: true` Bash so logs are inspectable and sessions survive across turns.
- Before booting, check ports (`lsof -i :3000 -i :8000 -i :8765 -sTCP:LISTEN`) and the worker (`ps aux | grep worker.py`) — if already running, reuse, don't double-boot.
- **Worker is required for imports.** RQ jobs on the `imports` / `respond_io` / `catalogue_render` / `media` / `flyer_read` queues (Excel imports, GRN lines, Respond.io sends, catalogue PDF exports / dealer-kit PDF renders, chatbot media extraction, dealer-kit flyer reads) run ONLY on the worker — the API process no longer drains them in-process. No worker = uploads enqueue but never process (a flyer read sits at `Processing` forever), and every `/external/media` turn waits out `media_sync_wait_seconds` then returns `pending`. Queue list is overridable via `WORKER_QUEUES` (see `worker.py`). The `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` prefix is mandatory on macOS: RQ forks a work-horse and the Obj-C runtime aborts it (signal 6) without it. `PGGSSENCMODE=disable` is mandatory for the same reason and a different signal: without it the forked child segfaults (signal 11) in libpq's Kerberos/XPC path the first time it opens a connection, and the job dies before it runs - see the lesson at the bottom of this file. Needs `REDIS_URL` reachable (`redis-cli ping`). Run `worker.py` with `ENABLE_SCHEDULER` unset locally (cron ticks aren't needed for most dev).
- During internal iteration, FE edits hot-reload on the `npm run dev` server — no action needed. **Every handoff to the user must be a prod build:** before you ask them to test/review :3000, kill dev and `npm run build && npm start` (never hand off a dev server). It matches their prod-build test env and surfaces build-only (RSC / server-component / `next build` type) errors dev hides. See "Frontend dev loop".
- Backend changes need no action beyond confirming uvicorn's reload log line — **except** edits to `app/tasks/*` (RQ tasks), which require restarting the Worker session.

## Architecture

### Auth boundary between FE and BE

NextAuth (frontend) issues the JWT. FastAPI validates it with the **same** `JWT_SECRET` / `JWT_ALGORITHM`. Tokens travel as `Authorization: Bearer <token>`.

Alternative principal: `X-API-Key` matching `EXTERNAL_API_KEY`. The legacy `system` principal has **no RBAC grants**, so for any non-trivial route also set `EXTERNAL_API_KEY_ACT_AS_USER_ID` to a real `users.id` whose role has the needed view permissions. The MCP server depends on this.

NextAuth routes (`/api/auth/*`) stay in Next.js. Everything else is FastAPI under `/api/v1/*`.

### Backend module structure

Routes are mounted in `app/api/v1/__init__.py` per domain (`master_data`, `order_management`, `inventory`, `procurement`, `marketing`, `forms`, `complaints`, `sla`, `resources`, `user_management`, `workflow_forms`, `incoming_stock`, `integrations`, `notifications`, `list_query`, `audit`, `system`, `external`, `public`).

Each router is wrapped in `Depends(require_module_enabled_with_api_key("<module_key>"))` from `app.modules.runtime.guards`. The guard short-circuits when `module_guard_strict` is off OR when the user has `superadmin`/`admin` OR when the tenant has no module rows yet (legacy installs). Per-tenant module enablement lives in `app.modules.runtime.installer`. Multi-tenant is stubbed: `_tenant_id_for_request()` returns `DEFAULT_TENANT_ID` until real tenant resolution lands.

`app/modules/<domain>/bootstrap.py` files are compatibility shims declaring `MODULE_KEY`. Domain code still lives under `app/api/v1/...`, `app/services/...`, `app/models/...`, `app/schemas/...`.

### List query / DataGrid contract

`app/services/list_query_registry.py` registers per-resource SQLAlchemy models, response schemas, and serializers. Frontend personalization (column order/visibility) is keyed by `listing_key` — either a permission slug (e.g. `order_management.orders.view`) or `<perm_slug>::<stable_id>`. Endpoints: `GET|PUT|DELETE /api/v1/list-query/column-config/{listing_key}`. See `docs/LISTING-COLUMN-PREFERENCES.md`.

### Embedding pipeline

Event-driven worker writes pgvector embeddings outside the request path. Producer = SQLAlchemy listeners in `app/services/embedding_change_listener.py` + `embedding_events.py`; consumer = `embedding_worker.py` over a queue. Source-of-truth is still the OLTP tables — embeddings are for RAG/semantic search only. Stock/order numerics intentionally not embedded (answer via SQL). See `pgvector-event-driven-functional-spec.md`.

### Frontend layering (enforced)

```
UI → Hooks (useXxxMutations / useXxxQuery) → feature service (services/xxxService.ts) → lib/api-client → backend
```

Hard rules from `docs/ARCHITECTURE-RULES.md`:

- Use `extractApiError(response, fallback)` from `lib/api-client` — do not hand-roll `response.json().catch(() => ({}))`.
- Use `buildDataGridParams(params, extra)` for DataGrid query strings — do not hand-build `URLSearchParams` for `page/limit/sort/dir/query`.
- User selects: `services/userSelectService` (no per-feature `getUsersSelect`).
- DataGrid listings MUST use `tableLayout: { width: 'fixed', columnsResizable: true }` with `columnResizeMode: 'onChange'`; columns need explicit `size` and long text uses `truncate` + `title`.

Mutation hooks: shared `useCreateMutation` / `useUpdateMutation` / `useDeleteMutation` patterns. On success: invalidate queries + toast. On error: extracted message + toast.

### CRUD UX standard (`docs/ADR-PRODUCT-STANDARDS.md`)

- List page = DataGrid + search/filters + "Add" toolbar button.
- Create/Edit = **modal by default**. Dedicated pages only for complex forms (multi-tab, nested entities) or file-centric flows (e.g. attachment bulk upload).
- View = dedicated `/{module}/{id}` detail page. **Always render every section**, even when empty — supply an explicit empty state with next-step CTA. Never hide a section on missing data.
- **Delete = hard delete + confirmation dialog**. Never use the browser's `confirm()`. Use `AlertDialog` from `@/components/ui/alert-dialog` (destructive button: `className="bg-destructive text-destructive-foreground hover:bg-destructive/90"`) or shared `ConfirmDeleteDialog` from `@/components/common/ConfirmDeleteDialog`. Bulk delete copy must include the count. Standard copy: "Confirm delete" / "This action cannot be undone".
- If retention is needed, add a **separate Archive** action with its own confirmation. Backend `DELETE` must be hard delete; do not name a soft-delete endpoint "delete".

#### View and Edit are the same layout (binding)

A record's **read view and its edit view must present the same structure**. Same tabs, in the
same order; same fields, in the same order, within each tab. Editing swaps a read-only value
for an input **in place** - nothing moves, appears, or disappears.

The reason is that the read view is what teaches the user where things are. If Edit reshuffles
them into a different arrangement, every edit starts with the user re-finding the field they
came to change, and a value they expected to see missing reads as data loss.

Concretely:

- **Group into tabs once**, and use the same tab set on both views. A record with more than one
  concern (identity vs configuration, say) gets a tab per concern rather than a long scroll.
- **Read-only metadata** (Created, Last Updated, ids) lives in the page header or a meta strip,
  **never inside a tab body**, because it has no edit counterpart and would otherwise make the
  two views differ.
- **Detail pages carry prev/next record navigation** via `components/common/RecordNavigation`.
  Reviewing a list of records one by one is the common case; making the user go back to the list
  between each is the thing that makes it feel unfinished. See `user-management/users/[id]` and
  `order-management/customers` for the established usage.
- **No explanatory prose in the UI.** A field gets a label, and at most a short hint of the form
  "what happens if I set this". Multi-sentence teaching text belongs in the user guide. This is
  the existing cursor rule ("No feature explanations inside the UI itself") applied to forms.
- **An optional select must be clearable.** `SearchableSelect` takes `clearable` - set it on
  every non-required select, or the user can change the value but never unset it.

### Cursor rules (apply to all `.ts`/`.tsx`)

- **No UUIDs in the frontend UI.** Resolve to human-readable identifiers.
- **No feature explanations inside the UI itself.** Put them in docs/FAQ.

### Backend service conventions

- App exception flow: raise `app.services.error_handler.AppException` (caught by the global handler in `app/main.py` and serialized to JSON with the correct status). Validation errors get a custom 422 handler.
- Audit listeners: registered at startup via `app.services.audit_service.register_audit_listeners`.
- Logging middleware: `app.middleware.logging_middleware.LoggingMiddleware`.
- Background scheduler initializes in `startup_event` in `app/main.py`.

## Env quick reference

Backend (`sorento_crm_backend/.env`): `DATABASE_URL`, `DIRECT_URL`, `JWT_SECRET`, `JWT_ALGORITHM`, `API_HOST`, `API_PORT`, `CORS_ORIGINS`, `REDIS_URL`, `AWS_*`, `CLOUDFRONT_*`, `STORAGE_DEFAULT_PROVIDER`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_CDN_DOMAIN`, `N8N_WEBHOOK_URL`, `EXTERNAL_API_KEY`, `EXTERNAL_API_KEY_ACT_AS_USER_ID`, `USE_REMOTE_TIME`, `RESPOND_*`, `DEALER_KIT_PRINT_BASE_URL`.

`DEALER_KIT_PRINT_BASE_URL` is where the PDF worker reaches the FRONTEND to render a catalogue (inside compose this is the service name, not the public hostname). It defaults to `http://localhost:3000`, so an unset value in a container renders nothing and the export fails on a render timeout.

Storage routing: each `attachments` row carries a `storage_provider` (`s3` or `r2`). New uploads use `STORAGE_DEFAULT_PROVIDER` (defaults to `s3`); reads (preview, download, presigned URL, webhooks) dispatch through `app/services/storage_router.py` so traffic for already-migrated rows is served via Cloudflare R2 + CDN while remaining rows continue to hit S3 + CloudFront. Use `scripts/migrate_attachments_to_r2.py` to copy bytes and flip provider per row.

Frontend (`sorento_crm_frontend/.env` or `.env.local`): `DATABASE_URL` (Prisma — NextAuth/user data only), `NEXTAUTH_SECRET` (must align with backend `JWT_SECRET` if sharing tokens), `NEXTAUTH_URL`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_BASE_PATH`, `GOOGLE_CLIENT_*`, `EXTERNAL_API_KEY`, `SMTP_*`, `STORAGE_*`, `RECAPTCHA_*`, `FRONTEND_BASE_URL`.

MCP (`sorento_crm_mcp/`): `CRM_BASE_URL`, `EXTERNAL_API_KEY`, optional `CRM_MCP_HOST/PORT/TIMEOUT/MAX_RESPONSE_BYTES/LOG_LEVEL`.

## Development methodology — three-phase loop

All non-trivial feature work follows three phases in order. Skipping or reordering is a process violation; if a phase can't be done (e.g. no design to prototype), call it out explicitly in the PR description.

### Phase 0 — Guided user experience (design the journey before the system)

**Every feature design starts from the guided user experience, never from the schema.** Before proposing entities, tables, endpoints or status graphs, write the journey:

- **Who** the actor is (end user / dealer / salesperson / office / technician / manager) and where they arrive from (WhatsApp link, portal, sidebar).
- **What the first screen shows**, and **what the system already knows** about them — anything knowable is never asked for.
- **Each step in order**, with the single decision the user makes at that step. Optimise for the **fewest decisions**, not for data completeness: the system infers, matches, extracts and pre-fills; the user confirms ("Did I get this right?").
- **What they hold at the end**, and what every other stakeholder is told automatically.

Any field derivable from something the user already gave us (a receipt photo, a phone number, an order, a policy) is **derived, not asked**. The data model is then designed **backwards from the journey** — schema serves the journey, never the reverse.

The journey is written at the top of the UAC file as its `Journey` section, and every AC traces to a step in it. A plan whose first section is a schema is rejected in review. See `PRINCIPLES.md` step 0 (governing).

### Phase 1 — Frontend prototype

Build the UI against **mock data / stubbed hooks** first, before any backend endpoint exists. Goal: nail UX, layout, states (loading / empty / error / partial), and the data contract the FE needs.

- Create components with hard-coded mock fixtures (`__mocks__/foo.ts` or inline `useState` seeds).
- Stub mutation/query hooks to return synthetic responses including `success`, `failed`, `processing`, `partial` cases.
- Verify in browser via agent-browser (headless) — click sidebar → reach the new screen → exercise every state. Screenshot the golden path + edge cases.
- Output: working FE branch where the new screens render correctly with mock data; a documented **expected API contract** (request shape, response shape, status enums) at the top of the relevant service file or in the plan doc.
- Do NOT touch backend code in this phase. Do NOT write tests yet — the UI shape may still shift after stakeholder review of the prototype.

### Phase 2 — Backend wiring + tests

Once the FE prototype is signed off, build the backend to match the contract documented in Phase 1, then wire the FE off mocks onto the real API.

- BE: models, migrations, schemas, services, routes. Match the Phase 1 contract exactly; if a deviation is unavoidable, update the contract doc and adjust FE in the same PR.
- FE: replace mocks with real hooks / services / `api-client` calls. Delete `__mocks__` fixtures unless they're reused by tests.
- **Tests must land in this phase, not deferred:**
  - **Vitest** (`sorento_crm_frontend/`): component tests for every new component covering loading / empty / error / data states. Hook tests for new query/mutation hooks. Use existing `vitest` + `@testing-library/react` patterns. Single test: `npx vitest run path/to/file.test.ts`.
  - **Playwright** (`sorento_crm_frontend/e2e/`): **a NEW spec is not currently added** - see "Persisted Playwright spec" below for the standing order and what covers a flow instead. The shape a spec would have had is still the target: one per user-facing flow, exercising the FE→BE→DB round-trip (click sidebar → action → assert outcome → assert the right `/api/v1/*` call), with real fixtures in `e2e/fixtures/` for AI / file flows.
  - **pytest** (`sorento_crm_backend/`): endpoint tests for every new route covering happy path + auth denial + validation error. Service-level tests for non-trivial business logic.
- Re-verify with agent-browser against the real stack: `localhost:3000` (FE) + `localhost:8000` (BE) + worker if relevant. Hit the same flows the prototype demonstrated; states should look identical with live data.
- Output: backend merged, FE off-mocks, all three test suites green in CI.

### Phase 3 — Code review

Run `/code-review` (or `/code-review ultra` for big diffs) on the merged Phase 1 + Phase 2 branch before opening PR for human review. Address findings with `/code-review --fix` or `/simplify` where appropriate. Then open the PR.

- Reviewer checklist: `documentation/reference/PR-CHECKLIST.md` plus — "did Phase 1 prototype get a screenshot in the PR description? did Phase 2 add tests (vitest + pytest) and a recorded evidence run for the user flow? does the contract doc match what shipped?"

### Why this order

- **Prototype first** stops us building a backend for a UI the user ends up rejecting. UX disagreements surface against a clickable mock, not a deployed feature.
- **Tests in Phase 2, not Phase 3** because once the contract is locked the wiring is the right time to pin it — adding tests after review usually means rushed tests.
- **Code review last** because reviewing a mocked FE in isolation tells you nothing about whether the data flow works end-to-end.

## Browser verification (agent-browser)

Frontend changes are not done until verified in a real browser. Type-check + Vitest = code correctness, not feature correctness. UI/flow changes MUST be exercised end-to-end before reporting complete.

**Use `agent-browser` (headless). Playwright MCP is retired for verification - do not use the `mcp__plugin_playwright_playwright__*` tools.** The committed specs under `e2e/` are unchanged and still run, but no NEW one is added - see "Persisted Playwright spec" below.

Two paths, pick one:

### 1. Interactive verification via agent-browser (preferred during a task)

`npx -y agent-browser@0.27.0 <command>` drives a headless Chromium-family browser against the running
dev server. It picks whatever it finds installed (Chrome, Brave, ...), so do not assume a specific
one. Headless is the default; `--headed` opts into a visible window. The browser persists between
invocations via a daemon, so each command is a separate shell call and `&&` chaining works:

```bash
npx -y agent-browser@0.27.0 open http://localhost:3000 && npx -y agent-browser@0.27.0 snapshot -i
```

**Read `agent-browser skills get core --full` before driving it.** That is the version-matched command
reference and workflow guide; it is the source of truth, not this section. What follows is only the
repo-specific policy plus the handful of commands that map onto our old MCP flow.

| Need | Command |
| --- | --- |
| Navigate | `open <url>` |
| See the page (accessibility tree with `@ref`s) | `snapshot`, or `snapshot -i` for interactive elements only |
| Click | `click <sel>` or `click @e2` (ref from the snapshot) |
| Find by role/text | `find role button click --name Submit` |
| Enter text | `fill <sel> <text>` (clear + fill), `type <sel> <text>` |
| Console output | `console` |
| Uncaught page errors | `errors` |
| Network calls | `network requests [--filter <pattern>]` |
| Screenshot | `screenshot [path]`, `--full`, `--annotate` for a labelled shot |
| Responsive check | `set viewport 375 812` / `set viewport 1280 800` |
| Finish | `close` |

Policy, unchanged from the MCP era:

- Ensure the FE dev server runs at `http://localhost:3000` (`npm run dev` in `sorento_crm_frontend/`, HMR) and BE at `http://localhost:8000`. For a final pre-handoff verification, do it against a prod build (`npm run build && npm start`) — see "Frontend dev loop".
- **Login for browser verification reads `E2E_EMAIL` / `E2E_PASSWORD` from `sorento_crm_frontend/.env.local` (gitignored).** The per-spec `*_E2E_EMAIL` / `*_E2E_PASSWORD` names used by the older `e2e/` specs (`REQUEST_BATCH_E2E_*`, `STOCK_E2E_*`, ...) are legacy aliases of the same pair. Names and path only ever appear in commits / status lines - never the values.
- **Always navigate to a feature by clicking through the sidebar / top nav from the home page - never `open` a deep URL directly.** Direct URL navigation hides nav-config bugs (missing entries, wrong `moduleKey`, broken permission gating, hidden behind a collapsed group). The first verification step for any new page is "open the sidebar group it belongs to and confirm the entry renders, then click it."
- Command flow: `open http://localhost:3000`, `snapshot -i` to find the relevant sidebar group button, `click @ref` to expand, `click @ref` the leaf entry, `snapshot` the destination, then `click` / `fill` / `select` and re-snapshot to assert state.
- Always check `console` (and `errors`) after the interaction. Treat unexpected error / warning output as a regression.
- Use `screenshot` for visual confirmation of CRUD flows (list → modal create → row appears → row edit → confirm-delete dialog → row gone).
- Use `network requests --filter /api/v1/` to verify the FE hit the expected endpoint with the right method/payload - confirms the hook → service → api-client chain wired correctly.
- Test the golden path AND edge cases: empty states (every section per CRUD UX standard), validation errors, delete confirmation copy, RBAC denial.
- `close` when done. Never `close --all` - it closes every session, including other agents' browsers on the same machine.

**The daemon's browser is SHARED across every agent on this machine, and it is one tab list.**
Another agent's `open` navigates the page out from under you, and nothing warns you: your next
`snapshot` / `console` / `network requests` silently describes *their* app. This is the worst
failure mode available here, because it looks like a bug in your feature rather than a mix-up -
you read a missing sidebar entry or a stack of console errors off a screen that was never yours.
Proven the hard way: an `open https://example.com` came back fine, and minutes later `get url`
reported `http://localhost:3090/signin`, another lane's dev server, in the only tab.

- `--session-name` does NOT isolate you. It is cookie/storage persistence, not a separate browser.
- **`get url` before you trust any read.** Confirm you are on the page you think you are on, at the
  start of a verification run and again after any gap between commands.
- `tab new` gives you your own tab, which helps, but tab focus is still global - re-check with
  `get url` rather than assuming the tab you made is the tab you are on.
- Verifying at a non-default port (`PORT=3090 npm run dev`) makes a stray page obvious on sight.

If unable to reach a browser (server down, sandboxed, daemon unresponsive), state that explicitly. Never claim a UI change works without browser verification.

### 2. Persisted Playwright spec (when the flow deserves regression coverage)

- **Do NOT add a new spec.** A standing order is that no project carries a playwright trace, and a new spec is a new trace. The ~40 pre-existing specs, `playwright.config.ts` and the dependency are untouched and still run; what replaces them repo-wide is an open decision. A flow that would have earned a spec is covered instead by a reproducible **agent-browser evidence run** (the exact steps, the network calls and the outcome written into the plan and the commit, so it can be re-walked), and the missing regression guard is logged in `documentation/backlogs/backlog.md`. The trade is spelled out in `documentation/plans/dealer-kit/PLAN-flyer-read-hardening.md` ("The e2e spec, and why it is not here").
- Specs live in `sorento_crm_frontend/e2e/`, config in `sorento_crm_frontend/playwright.config.ts` (chromium only, `baseURL` from `PORTAL_E2E_BASE_URL` ?? `http://localhost:3000`, viewport 1400x1600, single worker, no retries).
- Run all: `npm run test:e2e`. Run one: `npx playwright test e2e/foo.spec.ts`. Headed debug: `npx playwright test --headed --project=chromium`.
- Fixtures in `e2e/fixtures/` are real committed sample files (per memory rule: AI/file features test against real fixtures, not stubbed mocks). Add new fixtures alongside, do not gitignore them.
- Trace retained on failure (`trace: 'retain-on-failure'`); inspect via `npx playwright show-trace`.

### When to use which

- New CRUD page / modal / detail page → agent-browser interactive verification minimum.
- AI / file-extraction / portal flows → a recorded agent-browser evidence run, against a real fixture, is what a spec would have been. No new spec (see above).
- Pure visual / Tailwind tweak → an agent-browser `screenshot` is sufficient.

## Frontend dev loop (HMR by default; build only at handoff)

**The rule: `npm run dev` (HMR) for internal/team development; `npm run build && npm start` (prod) whenever handing off to the user.** These are the only two modes and the line between them is hard.

- **Internal dev / iteration → `npm run dev`.** One persistent Claude-managed server on :3000; FE edits hot-reload almost instantly, **no rebuild**. Use this for ALL coding + Claude-side agent-browser verification while a task is in progress. Running `npm run build` on every change is the slow path and is NOT how to iterate — a full prototype build cycle costs minutes and is the main thing that makes FE work drag.
- **Handoff to the user → `npm run build && npm start`, ALWAYS.** Any time you stop and ask the user to test / review / sign off on :3000, the running server MUST be a prod build — **never hand off a `npm run dev` server.** Kill dev, `npm run build && npm start`, then tell them :3000 is ready. This matches the user's prod-build test env AND surfaces build-only errors (RSC / server-component mistakes, type errors) that `next build` catches but `dev` hides. Also do a build before opening a PR.
- **Auth on dev:** the dev server must share the backend `JWT_SECRET` via `.env.local` (`NEXTAUTH_SECRET`) or NextAuth login flaps on :3000. Fix the env — do NOT prod-build every iteration to dodge it. If dev auth genuinely can't be made to work in a given environment, fall back to a prod build for login-gated Playwright verification (and say so).
- If HMR wedges (rare) or a change won't appear: `rm -rf sorento_crm_frontend/.next`, restart `npm run dev`, hard-refresh the browser.
- **Never `npm run build` while a `next start` is serving that same `.next`.** The build replaces chunk files under the running server, which keeps its old manifests, so pages come back half-rendered or empty. The tell is nasty because it looks like a code defect somewhere else entirely: `tests/test_dealer_kit_pdf_render.py` drives real Chromium at :3020 and failed 5 of 7 with "no tiles were drawn" and `min() iterable argument is empty` right after a rebuild, on a branch where nothing about rendering had changed. Kill the server, build, then start it again.

## PR checklist

`docs/PR-CHECKLIST.md` — verify CRUD pattern, delete confirmation + hard-delete semantics, empty states render, no duplication of `extractApiError` / `buildDataGridParams` / user-select helpers.

## Lessons learned (gotchas worth remembering)

- **Respond.io contact_id ≠ respond_io_id.** `PortalToken.contact_id` and the `contact_id` columns on complaints/stock_inquiries/purchase_requests store the internal `respond_contacts.id` (UUID). The Respond.io inbox URL (`/space/{space_id}/inbox/{...}`) and Respond message API need the contact's `respond_io_id`. Always resolve via `RespondContact` before building inbox URLs or calling Respond.io.
- **`respond_inbox_url` must be set at row creation** for the admin chat panel to work. Portal `_instantiate` was missing this; chat appears empty without it. Also exclude `respond_inbox_url` from any `_editable_fields` payload application.
- **Backfill scripts: idempotent JOIN-based "set to correct value where mismatch"** beats "update where NULL". The latter cannot fix prior runs that wrote wrong values; the former re-runs safely and corrects past errors.
- **Backend table names ≠ model class names.** `PurchaseRequestHeader` → table `purchase_requests`, not `purchase_request_headers`. `grep __tablename__` before writing raw SQL.
- **Hand-rolled `<table className="table-fixed">` overlaps columns** when content exceeds declared width. Always use shared `DataGrid` with explicit `size`, `tableLayout: { width: 'fixed', columnsResizable: true }`, and `truncate` + `title` for long text (see ARCHITECTURE-RULES).
- **Vitest + jsdom does not implement `scrollIntoView`.** Guard with optional chain — `ref.current?.scrollIntoView?.({...})` — so component tests don't TypeError.
- **`DataGridTable` DOES mount rows under jsdom.** The long-standing "it doesn't, so rows are untestable" note was wrong: `DataGrid` calls `useListingColumnPreferences`, which fetches the user's hidden/resized columns and renders skeletons until it answers. Under jsdom nothing answers. Mock it - `vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({ useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }) }))` - and rows, badges, per-row buttons and the pagination footer all assert normally. Proven by moving `BrochureImagePicker` onto the shared grid with all 35 of its tests intact.
- **When the interactive browser is unreachable, vitest is the fallback - but it is not UI verification.** The persisted-spec path needs the browser-verification login pair `E2E_EMAIL` / `E2E_PASSWORD` from `sorento_crm_frontend/.env.local` (per-spec `*_E2E_EMAIL` / `*_E2E_PASSWORD` names are legacy aliases), so it is often not available either. Component-level vitest verifies DOM structure / classes autonomously; do not claim full UI verification from it. Say explicitly that the browser could not be reached.
- **Don't silently duplicate chat / list panels across domains.** Complaint, stock_inquiry, purchase_request all share the Respond.io chat panel — render lives in shared `components/common/RespondChatList.tsx` so date pills, ticks, and selection rendering can't drift across the three.
- **AI assistant tool dropdown is sourced from the live MCP server, not the DB catalog.** `/api/v1/system/ai-assistant/tools` calls `MCPRuntimeClient.list_tools()` against `settings.ai_assistant_mcp_url` (default `http://localhost:8765/mcp`). Adding a tool to `sorento_crm_mcp.catalog.CATALOG` is not enough — you must restart the MCP process so FastMCP re-registers tools at startup. The persisted `mcp_tools` table is for AccessAgent ownership (`sync_catalog`), separate from the assistant settings dropdown.
- **Tools that don't proxy CRM HTTP endpoints need `external=True` on `ToolSpec`.** `_compile_tool` builds an HTTP-backed impl from `spec.method` + `spec.path` and would 404 for an external service like Outline. Set `external=True` on the spec, skip it in the compile loop, and register the real impl with `mcp.add_tool(...)` from a custom handler (see `register_user_guide_tools`). It still ends up in `mcp_tools` via `sync_catalog` so admins can assign it.
- **AI assistant chat renders raw text by default.** `**bold**`, `[link](/...)`, lists won't format unless the message is wrapped in `ReactMarkdown` (`AIAssistantBubble.tsx`). Internal links (`href` starts with `/`) route through `next/link`; external open in new tab. When adding new chat surfaces, mirror the same rendering or markdown shows up as raw asterisks.
- **Annotate user-guide menu paths with markdown links to FE routes**, not real-time URL resolution. The agent passes guide markdown straight through; if `[**Resource Management → Files**](/resource-management/attachment-directories)` is in the source, the user gets a clickable shortcut to the page. Single SoT in the guide, zero agent latency, deterministic. Add new menu paths to `scripts/annotate_user_guides_routes.py` and re-run; idempotent.
- **User guides are in Outline, not the repo at runtime.** End-user how-to lives at `https://doc.foundryx.my/collection/sorento-crm-BOoUtlxxTH` (`docs/user-guides/` is the editable copy). MCP tools `user_guides_search` + `user_guides_read` hit Outline directly. Two-way sync: `scripts/sync_user_guides_outline.py push|pull`, plus a GitHub Actions cron (`.github/workflows/outline-user-guides-sync.yml`) that pulls every 6h and opens a PR with diffs because the prod containers don't ship the markdown.
- **AI assistant must read before answering "how to".** The agent should call `user_guides_search` then `user_guides_read` then quote the steps with the markdown links intact — never just paste the doc URL and tell the user to read it. The system prompt enforces this via the **USER GUIDE PROTOCOL** section (`_user_guide_protocol_addendum`), auto-appended even when an admin sets a custom `system_prompt`.
- **Outline UI silently strips query-bearing markdown links from bold-wrapped link forms when a user opens the doc.** A push of `[**X**](/path?q=v)` (or its normalized form `**[X](/path?q=v)**`) survives `documents.update` and immediate `documents.info` fetches — the link IS stored. But as soon as a human opens the doc in the Outline web editor, ProseMirror re-serializes on the next auto-save and drops the link from labels containing spaces/digits/special chars (e.g. "Access Levels", "Upload 1 Attachment"), leaving plain `**X**`. Short single-word labels ("Upload") sometimes survive, making it look like a per-label bug. **Verify ALWAYS via API (`documents.info`) immediately after any sync, never trust Outline UI rendering as source-of-truth.** Use the script for source-of-truth and re-push after any user opens the doc. For deep-link-bearing UI shortcuts (`?guide_target=...`), this means the round-trip is fragile: prefer the URL-fragment form (`#guide_target=...`) once `GuideTargetSpotlight` is updated to read `window.location.hash`, since fragments are not part of Outline's link-validator path.
- **`re.sub` replacement strings parse `\X` as backreferences.** When injecting URLs into markdown via `re.sub(pattern, f"[**{label}**]({url})", text)`, any literal `\u` / `\g` / `\1`-`\9` in `url` raises `re.PatternError: bad escape`. Wrap replacements in a lambda — `pattern.sub(lambda _m, r=replacement: r, text)` — to bypass replacement-string parsing entirely. Hit by `_inject_route_links` in `ai_assistant_service.py` when guide markdown contained a literal `\u` from JSON-escaped Unicode.
- **Tailwind v4 `--primary` resolves to `oklch(...)`, not `H S% L%`.** `hsl(var(--primary) / 0.55)` is invalid CSS — browsers silently drop the entire declaration. For alpha overlays (e.g. spotlight pulse on `box-shadow`), use `color-mix(in oklab, var(--primary) X%, transparent)` instead. The class is applied but produces no visual effect, which looks like a JS bug (component never ran) rather than a CSS bug.
- **GuideTargetSpotlight: dialog-internal targets need MutationObserver fallback.** Buttons inside `Dialog` / `Popover` / `DropdownMenu` only mount when the user opens the parent. A simple `querySelector` retry window (e.g. 5×200ms) expires before that happens. The component now uses a 3-tier strategy: rAF → 5×200ms retry → `MutationObserver` on `document.body` for up to 30s. Strip the `?guide_target=` query param exactly once (idempotent flag) regardless of which tier finds the target. See `app/components/common/GuideTargetSpotlight.tsx`.
- **Re-injecting guide-authored deep links after LLM paraphrase needs a dynamic map, not the static `_ROUTE_MAP`.** When the agent reads a guide that contains `[**Upload**](?guide_target=...)`, the LLM often drops the link and emits plain `**Upload**`. The static `_ROUTE_MAP` only knows menu paths (Resource Management → Files etc.); button labels would never be re-wrapped. `_extract_guide_link_map(tool_calls)` scans the tool outputs for ALL `[Label](URL)` pairs and feeds them as `extra_map` to `_inject_route_links`. Bold-only re-injection — never plain — so a stray "upload" verb in prose is not auto-linked.
- **Two SLA systems share `conversation_sla_tracking`, discriminated only by `source_entity_type`.** Conversation SLA (n8n-created, max ONE open per contact — mirrors Respond.io's one-open-conversation-per-contact: unresolved = open, resolved = closed) has `source_entity_type` NULL / not in `FORM_SLA_TYPES`; form SLA stage rows (`form_sla_service`, per-entity, multi-active, never merged) have it in `FORM_SLA_TYPES`. Every contact-keyed conversation query MUST filter with `conversation_tracking_scope()` (sla_service.py) or it falsely matches form rows — the original bug: an active form row alone 409'd n8n's conversation create, and thread-assignee lookups could return a form row's assignee. n8n events touch conversation SLA only; CRM entity chat windows touch form SLA only (`get_tracking_by_source_entity`). Never split conversation SLA per entity — per-entity SLA is form SLA's job (decision log: `docs/plans/PLAN-conversation-sla-idempotent-create.md`).
- **Conversation-SLA create is idempotent, not 409.** Active row exists → 200 with `already_active: true`, `message_id` refreshed, clocks/assignee untouched, NO assign event log. Resolved row → overwrite-in-place (history lives in event logs, which survive overwrite — FK by tracking id). DB-level singleton enforced by partial unique index (migration 180: `respond_contact_id WHERE is_resolved=false AND (source_entity_type IS NULL OR ='conversation')`). The backend owns the initial `assign` event log; n8n's routing sub-workflow must NOT post one.
- **`create_event_log` interprets NAIVE datetimes as Malaysia time (UTC+8), but tracking columns store naive UTC.** Passing `tracking.due_at` (naive UTC) straight into an event-log payload silently shifts it −8h during normalization. Wrap with `_to_aware_utc()` first. Applies to `event_at`, `from_time`, `due_at`, `last_reminder_at`.
- **Post-commit side effects must be best-effort.** A side effect that runs AFTER the main row commits (e.g. `_write_assign_event_log` after `create_tracking` commit) must catch + warn, never raise: the caller gets a 500 for an operation that actually succeeded, and the retry takes the idempotent path which never backfills the missed side effect. Same family as the idempotent-marker pattern: service smuggles `_already_active` / `_already_resolved` / `_overwrote_resolved` as instance attrs; routes read them with `getattr(tracking, "_x", False)` and expose clean response fields — markers die on re-query, so extract them BEFORE calling `get_tracking()` again.
- **Tests run on Postgres ONLY, NEVER sqlite (hard rule, see PRINCIPLES.md).** Do not build a `sqlite:///:memory:` engine, register `@compiles(..., "sqlite")` shims, or mutate shared `Base.metadata` column types (`col.type = JSON()`). Two concrete failure modes this caused: (1) sqlite's NUMERIC affinity coerces a mostly-zero UUID (e.g. the Sorento company id `00000000-...-0001`) to the integer `1`, so a later read blows up in `uuid.UUID(1)` -> `'int' object has no attribute 'replace'`; (2) a sqlite fixture rewriting `col.type` on the process-global metadata leaks into other tests' `create_all` schema (dropped FKs, wrong column types), and the breakage surfaces only in a full-suite run, in a file that touches no sqlite. Use `tests/_pg_fixture.py`: `blank_session()` for an isolated blank schema (the `companies` table is auto-seeded with Sorento via an `after_create` hook in `conftest.py`, so auto-stamped `company_id` FKs resolve), or `SessionLocal` inside a rolled-back transaction. Seed REAL FK targets (category, uom, import_jobs parent, ...) - Postgres enforces the constraints sqlite silently ignored, so a loose invented UUID that "worked" on sqlite now aborts the transaction. Mock-chain tests (`qm.filter.return_value = qm`) still break silently when a query gains `.order_by()` - the auto-created child mock's `.first()` returns a truthy MagicMock instead of your sentinel.
- **CI's database has NO data. Tests that borrow existing rows pass locally and fail in CI.** The local `DATABASE_URL` is a copy of production, so `SELECT id FROM sla_policies LIMIT 1`, "the live `complaint`/`main` stage config", and "whatever roles hold `.approve`" all silently resolve to something real. CI runs a freshly migrated Postgres where every one of those is `None`/absent, and the dependent INSERT then dies on a NOT NULL FK (`null value in column "policy_id" violates not-null constraint`) - one borrowed lookup produced 16 failures. **Every test seeds its own chain**: policy -> config -> entity -> tracker, each with a marker prefix, never `LIMIT 1` off an existing table and never an assertion about a production row. Where the thing under test IS seed/config wiring, import the migration and run its `upgrade()` inside a rolled-back transaction (seeding the pre-migration row when absent) rather than asserting the live row - that tests the code instead of the environment. If a suite genuinely needs shared reference data, write a seeder fixture; do not assume it is there. **The only honest check is an empty database**: build the schema on a scratch DB (`createdb`, `Base.metadata.create_all`, needs `CREATE EXTENSION vector` as a superuser), confirm the tables you depend on are empty, and run the suite against it before pushing. Marker-scoped cleanup must delete children first (trackers -> entity -> config -> policy).
- **A migration-seeded reference table needs `__company_shared__ = True`, or its own seeds are invisible.** `build_company_predicate` (`app/services/company_scope.py`) compiles an OWNED `CompanyScopedMixin` table to `company_id IN (scope)`, which excludes the NULL-company rows a migration seeds; only a `__company_shared__` table gets the `OR company_id IS NULL` arm. The symptom is split by principal and reads as an auth bug: an API-key caller (unscoped) sees all the seeds, a logged-in user sees none, so the same endpoint returns five rows to n8n and an empty list to the FE. Hit by `promotion_types` (migration 361), whose five seeded rows vanished from every ORM query under a real user scope.
- **NEVER use em-dashes (or en-dashes) in any writing** - code comments, commit messages, PR bodies, docs, chat. Use a spaced hyphen, comma, colon, or parentheses instead.
- **Suffixed NextAuth session cookie breaks `getToken` → refresh-logout.** `auth-options.ts` renames the session cookie with `NEXTAUTH_COOKIE_SUFFIX` (e.g. `next-auth.session-token.sorento`) so :3000/:3001 instances don't clobber each other (browsers scope cookies by host, ignoring port). But `/api/auth/token` and `lib/api-proxy.ts` called `getToken()` with the DEFAULT name → found nothing → 401 on every FastAPI call after a hard refresh, while `/api/auth/session` stayed valid (so it looked like "logged out" but the NextAuth session was fine). Fix: single source of truth `lib/auth-cookie.ts` `sessionTokenCookieName()`, passed as `cookieName` to every `getToken` caller AND used in auth-options. Never hardcode `next-auth.session-token`.
- **Deep-link-after-login is the `(protected)` layout's job.** It redirects unauthenticated users to `/signin?callbackUrl=<full relative URL>` — capture `pathname + search + hash`, NOT just `pathname` (else query strings are dropped). The signin page honours same-origin (`/`, not `//`) callbacks. Every internal route renders through this one layout, so fixing it here is the system-wide solution. Portal contact links live under `(auth)` (`/view`, `/portal` + OTP confirm-identity) — a separate NextAuth-independent flow that never hits this layout.
- **Every Respond.io send must write an `integration_log` (the "Respond outbox") on success AND failure.** Local testing runs with intentionally-wrong creds, so a 401'd send must still be logged, not just flip `notification_delivery.status=failed`. Mirror `_send_and_log` (respond_io_tasks). `send_text_or_template` stamps the ACTUALLY-attempted payload (text vs template) onto the raised exception (`_attach_send_context`) so the outbox shows the truth — a closed-window failure logs as a *template* attempt, not a default text payload. `integration_log.business_id` is a UUID column: use `notification.id`, never a composite `source_entity_id` like `<user>:<date>:manual:<ts>`.
- **Respond sends use the WORKSPACE key, not env `RESPOND_API_KEY`.** `RespondClient` resolves the per-contact/default workspace key from `respond_workspaces` first; the env key is a deprecated last-resort fallback. A bad/placeholder workspace key 401s every send while `settings.respond_api_key` is perfectly valid — verify which key the send path actually uses (`RespondClient.for_identifier(...)`), don't assume env.
- **Form-SLA stage is identified by `(source_entity_type, team_set_code)`** (the tracker copies `team_set_code` from the spawning config; that pair is unique per stage). Use it for next-action derivation, escalation-notify gating, etc. Reusable tier helper `AccessAgentService.resolve_team_with_tier_fallback(agent, start_tier, team_set)` → first existing team at-or-above the tier — used by BOTH initial assignment (`_start_for_config`) and escalation (`_escalate_tracker`) so a missing intermediate tier is skipped, not fatal. Default-approver override: PR/SF approval stage routes to the form's configured default approver at THEIR tier when they're a team member.
- **SLA notify is a matrix: stage bool AND user per-event toggle.** Stage `notify_assignee` (assignment) + `notify_on_escalation` (escalation) gate the event; per-user `notify_email_on_{assignment,escalation}` / `notify_whatsapp_on_{assignment,escalation}` gate the channel. In-app always sends when the stage allows. `create_with_channel_preferences` takes `email_pref_attr` + `whatsapp_pref_attr`; `_notify_assignee(kind)` passes the per-event attrs. WhatsApp still also needs a linked RespondContact.
- **`get_user`/`get_me` build a manual `UserResponse(**user_dict)` that silently drops any field not listed.** New User columns (e.g. the notify toggles) won't reach the FE until added to BOTH manual dict builders — `UserResponse(UserBase)` inheriting the field is NOT enough. Symptom: a toggle always renders its default, never the saved value.
- **Staff team-notification emails link to the in-system detail page** (`/procurement-management/...{id}`), NOT the public `/view?token=` page — recipients are internal staff (and the deep-link-after-login carries them back post-login). Contact-facing messages keep the public token link. Each entity has a separate `_build_*_internal_url` vs `_build_*_view_url`.
- **Responsive detail headers: `flex items-center justify-between` does NOT wrap** — on mobile the action buttons can't fit beside a long wrapping title, so they overlap it AND force page-wide horizontal overflow (cutting the whole form). Use `flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between` on the header, `min-w-0 break-words` on the title block, `flex-wrap` on the actions. Applied uniformly across PR/SF, complaint, stock-inquiry details.
- **Status pill colour is centralized in `lib/status-pill.ts`** (soft pastel, matching complaints) — reused across PR/SF/stock-inquiry list+detail. `getDisplayStatus` for PR/SF must prioritize the lifecycle `status` (terminal CS states: processed_by_cs/closed/submitted) over `approval_status`, or the list disagrees with the detail page and the portal (e.g. an approved-then-processed PR must read "Processed by CS", and a portal-submitted PR "Submitted" not "Draft"). The portal `SUBMISSION_STATUS_LABELS` map must cover the same codes.
- **react-query staleness on entity mutation: key dependent queries on the entity's changing field.** The in-form SLA escalation banner reads the active-tracker query; key it on `updated_at` (PR/SI) / `status` (complaint) so it refetches the instant a resolve/approve spawns the next stage — otherwise the banner shows the old stage's reason until a manual refresh.
- **`system_settings` MUST be a singleton, but nothing enforced it.** The table has no `created_at`, and every read/write is `db.query(SystemSetting).first()` with **no ORDER BY**. With two rows present, the GET serializer, `_update_general_settings_impl` (PUT), and any service reader non-deterministically hit *different* rows — a settings save returns 200 but the value doesn't appear (PUT wrote one row, GET reads the other). Masked whenever the duplicate rows hold identical values. Migration 253 dedupes to one row (`min(ctid)`) + a unique index on the constant expression `((true))` so a second row can never be inserted. When adding a `system_settings` column, add it to BOTH manual builders (the GET dict AND `SystemSettingUpdate`) — inheriting the field is not enough (same family as the `get_user` manual-dict-drops-fields rule).
- **`apiFetch('/api/<domain>/...')` maps straight to the FastAPI backend `/api/v1/<domain>/...`** (`lib/api.ts` rewrite table), BYPASSING any Next.js `app/api/.../route.ts` proxy. So a dedicated route.ts proxy for a settings save is never hit; point the mutation at an existing backend route instead (POST `/general` setattrs any provided snake_case column). Only plain `fetch('/api/...')` uses the Next route.ts proxies.
- **MCP `updated_at` must be emitted as NAIVE Malaysia wall-clock, not offset-aware `+08:00`.** The backend serializes `updated_at` as naive UTC (no `Z`). `_to_malaysia_iso` converting it to aware `...+08:00` is technically correct, but downstream consumers (n8n/luxon) re-convert an offset-aware timestamp back to UTC for display — undoing it (09:28 MYT rendered as 01:28). Emit `dt.astimezone(_MALAYSIA_TZ).replace(tzinfo=None).isoformat()` (naive). Generic on the `updated_at` key in `_sanitize_tool_response` → fixes stock-balance, order-list, every tool at once.
- **Complaint↔DO auto-fulfilment invariants.** (1) A DO counts as "delivered" only when BOTH `actual_delivery_date` is set AND `order_status` ∈ {delivered, completed} — an AND, evaluated against the INCOMING status in `update_order` so moving a DO off DELIVERED unfreezes Remarks CS in the same save. (2) The auto-linker only links complaints in `LINKABLE_STATUSES = {processed_by_cs, fulfilled}`; a `submitted` complaint named in Remarks CS is skipped and does NOT retro-link when later processed (reconcile only re-runs on ORDER-side changes — re-save the DO). (3) The team delivery email sends ONE email PER member (each as To), never To=first + CC=rest — CC recipients were silently dropped by mail-server/client filtering so only the To member received it. (4) Notify tiers are DB-configurable (`system_settings.complaint_do_delivered_notify_tiers`, Settings → Complaints) resolving DB → env → default `1,2`.
- **MCP stock-balance hides on-hand=0 rows zeroed by a SYSTEM_ADJUSTMENT.** The MCP always sends `exclude_zero_system_adjustment=true`; the backend filters via a correlated latest-`stock_ledger` scalar subquery on `(product_id, warehouse_id)` — a genuine 0 (last movement an import/sale, or no ledger) is still returned. FE stock list is unaffected (param defaults false).
- **AI assistant prompts live in a DB registry (M1), not hardcoded.** All prompts resolve through `app/services/ai_prompt_registry.py` — `PROMPT_KEYS` (4 active: `reformulator`/`router`/`agent_system`/`synthesizer` + 5 dormant) with immutable versions (`ai_prompt_versions`, `max+1` per name) + movable labels (`ai_prompt_labels`, `production`/`staging`). `get_prompt(db,name,label)` = TTL cache + **hardcoded fallback when DB-unreachable** (the old inline strings are now `fallback()` funcs — a fallback returns `version=None`, never raises). Publish = move label (no redeploy); busts the cache. Edit in FE at `system-management/ai-assistant/prompts/`. **`config.system_prompt` is deprecated/read-ignored** — the registry `agent_system` key is the SoT (column kept one release). Every turn stamps `metadata_json.prompt_versions=[{name,version}]` per LLM call (bridge to M2 trace).
- **The prompt dry-run (`POST .../prompts/{name}/test`) is END-TO-END, not per-node.** It runs the WHOLE assistant turn (`reformulator → RAG → agent_system → synthesizer`) with ONLY the tested key overridden, and shows the **final synthesizer answer** — you do NOT see an individual node's raw output (e.g. the reformulator's own text). Per-node in/out inspection = M2 trace (`PLAN-ai-assistant-node-trace.md`). Also: dry-run runs the **saved** selected version, not the unsaved editor buffer; it deletes the throwaway conversation after; and it **strips write-capable MCP tools** (`_is_write_tool`: `*_submit`/`*_create`/`*_link`) so a test can't persist a real complaint/PR/ticket. Don't instruct `reformulator` to emit JSON — downstream RAG expects a natural-language standalone query; JSON routing is the `router`/M2.5 job.
- **Prompt-registry save-validation returns a TOP-LEVEL body, not the `AppException` envelope.** `POST .../prompts/{name}/versions` on an unknown `{{token}}` returns `422 {error, unknown_tokens, missing_vars}` via raw `JSONResponse` (bypasses `response_model`) — unknown token = hard block, missing declared var = 201 + soft warn. FE reads those fields directly (can't use `extractApiError`, which is string-only). Declared vars are a fixed property of the KEY in `PROMPT_KEYS`, not free-form.
- **Form handling-lock "escalated" = `escalated_at` stamped, NOT `current_tier > 1`.** Some form-SLA configs START above tier 1: `project_sales` begins at tier 2 (no tier-1 team); PR/SF approval routes to the configured default approver at THEIR tier (2/3) via `_start_for_config`. So a fresh, never-escalated tracker sits at tier 2/3 with `escalated_at IS NULL`. Keying the lock on `current_tier > 1` falsely showed the "Escalated to Tier N — claim it" banner + disabled CTAs on an approver-assigned form. `escalated_at` is set ONLY by `_escalate_tracker` (alongside `escalation_reason` — always in lockstep), never on initial assignment. Gate both sides on it: FE `resolveHandlingLockState` (`!activeTracker.escalated_at`), BE `handling_lock_service._is_escalated()` (used by `assert_can_act_on_form` + `_assert_claimable`). Type-agnostic across all `FORM_SLA_TYPES`. Assignment to a high tier ≠ escalated; only a real SLA breach that escalates locks the form.
- **The in-form lock banner and SLA-escalation banner are TWO separate queries** — a manual "Escalate" must invalidate BOTH or the lock banner lags a reload. Lock banner ← `useHandlingLock` → `form-sla-tracking` (key `form-handling-tracker`); SLA banner ← `SlaActiveTrackerControls` → `conversation-sla-tracking/by-source` (key `form-sla-trackers`). The gear-menu escalate handlers invalidated only `form-sla-trackers`, so the SLA banner updated live but the lock banner stayed stale. Fix: `useHandlingLock()` exposes `refresh()`; call it after `escalateFormTracking` in every form detail page (stock-inquiry / complaint / PR-SF). Verify via `agent-browser network requests --filter form-sla-tracking` that the GET refetches right after the escalate POST.
- **"One client is jammed, another is fine" does NOT rule out a blocked event loop - prod runs 4 gunicorn workers.** `sorento_crm/docker-compose.yml` starts `gunicorn --workers 4 --timeout 120 --keep-alive 5`, so an `async def` route doing heavy synchronous work kills ONE worker for its duration and leaves three serving. The desktop that started the slow request is additionally parked on it and can hold keep-alive connections pinned to the dead worker; a phone on fresh connections lands on a live one and looks healthy. The discriminating measurement is a single-worker local run: poll a cheap endpoint from a second shell while the slow request is in flight. The flyer read measured `GET /health` at **57.5s** that way (`documentation/plans/dealer-kit/PLAN-flyer-read-hardening.md` has the full method). Fix is `run_in_threadpool` from `fastapi.concurrency`, already the idiom in `app/api/v1/resources/attachments.py`, or plain `def` when the handler has no await worth keeping (FastAPI then threadpools the whole handler; portal `ai_extract` and `preview_spec_search`) - keep `async def` only where an `await file.read()` enforces a size ceiling as bytes arrive, as the flyer upload does. Check first that the hot library releases the GIL, or the threadpool buys nothing (PyMuPDF does; measure loop tick lag in a thread to confirm for a new one). About 40 more handlers of this shape are listed in `documentation/plans/ai-extract/PLAN-ai-extract-off-the-loop.md` (BL-009).
- **On macOS an RQ work-horse SEGFAULTS (signal 11) the moment it opens a NEW psycopg2 connection, and it looks like your job crashed.** The child's `psycopg2.connect` goes into libpq's `PQconnectPoll` -> `pg_GSS_have_cred_cache` -> `gss_acquire_cred` -> `libkrb5`'s `api_macos_ptcursor_next` -> `libxpc`, and XPC is not fork-safe: the forked child dies before a single line of the task runs. RQ reports only `Work-horse terminated unexpectedly; waitpid returned 11`, the job never marks itself failed, and any row the task was supposed to flip stays `processing` forever. `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` does NOT cover it - that is the Obj-C abort (signal 6), this is a segv on a different path. It fires whenever the PARENT already touched XPC/GSS, which `ENABLE_SCHEDULER=true` guarantees because APScheduler opens its own DB connections before the first fork. Fix: run the worker with `PGGSSENCMODE=disable` (libpq then skips the credential-cache probe entirely). Measured on the flyer read: scheduler on, 3 of 3 jobs segfaulted; scheduler off, or `PGGSSENCMODE=disable` with the scheduler on, the real 36-page flyer completes in 25 s. **Linux is unaffected** - the faulting frames are literally macOS-only (`api_macos_ptcursor_next`, `libxpc`), so production containers do not take this path. Suspect it FIRST for "the job enqueued and nothing happened" on a dev Mac, and note it kills every queue, not just the one you are working on: the identical stack is in `~/Library/Logs/DiagnosticReports/Python-*.ips` from other lanes' worker deaths.
- **A docstring asserting a performance number is load-bearing, and goes stale silently.** The flyer routes justified doing extraction in-request with "the real 36 page flyer takes about a second" and named their own threshold ("stops holding at roughly ten seconds"). Measured: 17-18s quiet. Nothing failed, so nothing caught it, and every later decision inherited the wrong premise. When a comment justifies a design with a number, record what it was measured against and re-measure before reusing it.
- **agent-browser `click` on an off-screen element is a silent no-op.** Sidebar accordion buttons, listbox options in a `SearchableSelect`, and pagination buttons below the fold return a valid `@ref` from `snapshot` but the click does nothing (no error, no navigation, no network call), and `find role button click --name` does not help. Run `scrollintoview @ref` before `click @ref` for anything inside a scroll container. Cost a full evidence run on the spec-verification worklist before it was spotted.
- **One container, several suppliers: `inbound_shipment_lines.supplier_id` owns the line, and an upload replaces only its own supplier's lines.** Since migration 374 the line key is `(shipment_id, product_id, supplier_id) NULLS NOT DISTINCT` (PG 15+). `create_shipment` with a supplier stated (header or line) deletes that supplier's lines plus unattributed lines for the same products; with none stated (n8n PDF path) it still replaces all. Header `supplier_id` is DERIVED (one distinct line supplier -> it, mixed -> NULL), so never filter shipments by the header alone - use `shipment_supplier_predicate` (header OR line) or `coalesce(line, header)`. `POST /scm/packing-lists/apply` requires `supplier_id`. Edits go through `update_shipment`'s upsert-by-(product, supplier); a product from two factories edited without a per-line supplier is a 409, not a guess.
- **A reusable `exists()` predicate needs an explicit `.correlate(<parent>)`.** `shipment_supplier_predicate` auto-correlated fine in a plain query but raised `Select statement ... returned no FROM clauses due to auto-correlation` inside `incoming_stock_service`, whose outer query already selects from `inbound_shipment_lines` through a subquery, so the EXISTS lost both FROMs. Pin the correlation when the predicate is shared across queries of different shapes; the failure is a 500 only on the callers no test covers.
- **A baseline `git checkout <commit>` in a shared worktree leaves it detached, and later commits land off the branch.** A reviewer comparing tsc/vitest output against the base commit did exactly that; two later commits sat on a detached HEAD until `git branch -f <branch> HEAD && git checkout <branch>` repaired it. Compare with `git stash` / `git show <rev>:<path>` / a throwaway `git worktree add`, never by checking out a commit in the tree other agents are committing to.

## Agent skills

### Delivery pipeline

Non-trivial feature work runs through **`/feature`** (`.claude/skills/feature/SKILL.md`), which
executes the mandatory order in `PRINCIPLES.md` and calls the `mattpocock-skills` plugin at each
slot. Two overrides: UAC + PLAN **files** under `documentation/plans/` are the contract (tickets
are only the queue), and the frontend mock is built before any backend code (so `/implement` is
scoped to Phase 2). See the skill map at the bottom of that file.

### Session handoff (instead of autocompact)

Long sessions take a deliberate cut rather than letting autocompact pick one: **`/handoff`**
writes a resume document to `.claude/handoffs/<UTC ts>-<slug>.md` (gitignored, worktree-local),
the user runs `/clear`, then **`/resume-handoff`** restores from it - re-reading the artifacts
the document points at and re-checking its "Assumed, not verified" section before acting. An
agent cannot clear its own conversation, so the middle step is the user's; an unattended agent
instead reports `blocked:` with the document path and its supervisor resumes from it. **Never run
`/compact`** - it is the lossy summary this replaces, not a lighter alternative to it. Upstream
`/mattpocock-skills:handoff` stays available for work that leaves this checkout (it writes to
the OS temp dir and has no resume half). See `documentation/agents/session-handoff.md`.

### Issue tracker

GitHub Issues on `jayson-odoo/sorento-crm`, via the `gh` CLI. See `documentation/agents/issue-tracker.md`.

### Triage labels

Canonical five-label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `documentation/agents/triage-labels.md`.

### Domain docs

Multi-context: `CONTEXT-MAP.md` at the root points at two glossaries; ADRs in `documentation/adr/`. See `documentation/agents/domain.md`.
