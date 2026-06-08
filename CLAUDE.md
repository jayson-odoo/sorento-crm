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
| Worker   | `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES venv/bin/python worker.py` (in `sorento_crm_backend/`) | —    | **No reload.** Restart manually after editing any RQ task (`app/tasks/*`). |
| Frontend | `npm run build && npm start` (in `sorento_crm_frontend/`)                                       | 3000 | **No HMR.** After any FE change: kill the session, `npm run build && npm start` again |
| MCP      | `CRM_BASE_URL=http://localhost:8000 EXTERNAL_API_KEY=<from backend .env> backend venv's python -m sorento_crm_mcp` (in `sorento_crm_mcp/`; package installed in the backend venv) | 8765 | Restart manually after MCP code/catalog changes |

- Run each as `run_in_background: true` Bash so logs are inspectable and sessions survive across turns.
- Before booting, check ports (`lsof -i :3000 -i :8000 -i :8765 -sTCP:LISTEN`) and the worker (`ps aux | grep worker.py`) — if already running, reuse, don't double-boot.
- **Worker is required for imports.** RQ jobs on the `imports` / `respond_io` queues (Excel imports, GRN lines, Respond.io sends) run ONLY on the worker — the API process no longer drains them in-process. No worker = uploads enqueue but never process. The `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` prefix is mandatory on macOS: RQ forks a work-horse and the Obj-C runtime aborts it (signal 6) without it. Needs `REDIS_URL` reachable (`redis-cli ping`). Run `worker.py` with `ENABLE_SCHEDULER` unset locally (cron ticks aren't needed for most dev).
- After every frontend change set, rebuild + restart the FE session **proactively** (don't wait to be asked) and tell the user when :3000 is ready to test.
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

### Cursor rules (apply to all `.ts`/`.tsx`)

- **No UUIDs in the frontend UI.** Resolve to human-readable identifiers.
- **No feature explanations inside the UI itself.** Put them in docs/FAQ.

### Backend service conventions

- App exception flow: raise `app.services.error_handler.AppException` (caught by the global handler in `app/main.py` and serialized to JSON with the correct status). Validation errors get a custom 422 handler.
- Audit listeners: registered at startup via `app.services.audit_service.register_audit_listeners`.
- Logging middleware: `app.middleware.logging_middleware.LoggingMiddleware`.
- Background scheduler initializes in `startup_event` in `app/main.py`.

## Env quick reference

Backend (`sorento_crm_backend/.env`): `DATABASE_URL`, `DIRECT_URL`, `JWT_SECRET`, `JWT_ALGORITHM`, `API_HOST`, `API_PORT`, `CORS_ORIGINS`, `REDIS_URL`, `AWS_*`, `CLOUDFRONT_*`, `STORAGE_DEFAULT_PROVIDER`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_CDN_DOMAIN`, `N8N_WEBHOOK_URL`, `EXTERNAL_API_KEY`, `EXTERNAL_API_KEY_ACT_AS_USER_ID`, `USE_REMOTE_TIME`, `RESPOND_*`.

Storage routing: each `attachments` row carries a `storage_provider` (`s3` or `r2`). New uploads use `STORAGE_DEFAULT_PROVIDER` (defaults to `s3`); reads (preview, download, presigned URL, webhooks) dispatch through `app/services/storage_router.py` so traffic for already-migrated rows is served via Cloudflare R2 + CDN while remaining rows continue to hit S3 + CloudFront. Use `scripts/migrate_attachments_to_r2.py` to copy bytes and flip provider per row.

Frontend (`sorento_crm_frontend/.env` or `.env.local`): `DATABASE_URL` (Prisma — NextAuth/user data only), `NEXTAUTH_SECRET` (must align with backend `JWT_SECRET` if sharing tokens), `NEXTAUTH_URL`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_BASE_PATH`, `GOOGLE_CLIENT_*`, `EXTERNAL_API_KEY`, `SMTP_*`, `STORAGE_*`, `RECAPTCHA_*`, `FRONTEND_BASE_URL`.

MCP (`sorento_crm_mcp/`): `CRM_BASE_URL`, `EXTERNAL_API_KEY`, optional `CRM_MCP_HOST/PORT/TIMEOUT/MAX_RESPONSE_BYTES/LOG_LEVEL`.

## Development methodology — three-phase loop

All non-trivial feature work follows three phases in order. Skipping or reordering is a process violation; if a phase can't be done (e.g. no design to prototype), call it out explicitly in the PR description.

### Phase 1 — Frontend prototype

Build the UI against **mock data / stubbed hooks** first, before any backend endpoint exists. Goal: nail UX, layout, states (loading / empty / error / partial), and the data contract the FE needs.

- Create components with hard-coded mock fixtures (`__mocks__/foo.ts` or inline `useState` seeds).
- Stub mutation/query hooks to return synthetic responses including `success`, `failed`, `processing`, `partial` cases.
- Verify in browser via Playwright MCP — click sidebar → reach the new screen → exercise every state. Screenshot the golden path + edge cases.
- Output: working FE branch where the new screens render correctly with mock data; a documented **expected API contract** (request shape, response shape, status enums) at the top of the relevant service file or in the plan doc.
- Do NOT touch backend code in this phase. Do NOT write tests yet — the UI shape may still shift after stakeholder review of the prototype.

### Phase 2 — Backend wiring + tests

Once the FE prototype is signed off, build the backend to match the contract documented in Phase 1, then wire the FE off mocks onto the real API.

- BE: models, migrations, schemas, services, routes. Match the Phase 1 contract exactly; if a deviation is unavoidable, update the contract doc and adjust FE in the same PR.
- FE: replace mocks with real hooks / services / `api-client` calls. Delete `__mocks__` fixtures unless they're reused by tests.
- **Tests must land in this phase, not deferred:**
  - **Vitest** (`sorento_crm_frontend/`): component tests for every new component covering loading / empty / error / data states. Hook tests for new query/mutation hooks. Use existing `vitest` + `@testing-library/react` patterns. Single test: `npx vitest run path/to/file.test.ts`.
  - **Playwright** (`sorento_crm_frontend/e2e/`): one spec per user-facing flow that exercises the FE→BE→DB round-trip (click sidebar → action → assert outcome → check `browser_network_requests` for the right `/api/v1/*` call). Add real fixtures to `e2e/fixtures/` for AI / file flows.
  - **pytest** (`sorento_crm_backend/`): endpoint tests for every new route covering happy path + auth denial + validation error. Service-level tests for non-trivial business logic.
- Re-verify with Playwright MCP against the real stack: `localhost:3000` (FE) + `localhost:8000` (BE) + worker if relevant. Hit the same flows the prototype demonstrated; states should look identical with live data.
- Output: backend merged, FE off-mocks, all three test suites green in CI.

### Phase 3 — Code review

Run `/code-review` (or `/code-review ultra` for big diffs) on the merged Phase 1 + Phase 2 branch before opening PR for human review. Address findings with `/code-review --fix` or `/simplify` where appropriate. Then open the PR.

- Reviewer checklist: `docs/PR-CHECKLIST.md` plus — "did Phase 1 prototype get a screenshot in the PR description? did Phase 2 add tests (vitest + playwright + pytest)? does the contract doc match what shipped?"

### Why this order

- **Prototype first** stops us building a backend for a UI the user ends up rejecting. UX disagreements surface against a clickable mock, not a deployed feature.
- **Tests in Phase 2, not Phase 3** because once the contract is locked the wiring is the right time to pin it — adding tests after review usually means rushed tests.
- **Code review last** because reviewing a mocked FE in isolation tells you nothing about whether the data flow works end-to-end.

## Browser verification (Playwright)

Frontend changes are not done until verified in a real browser. Type-check + Vitest = code correctness, not feature correctness. UI/flow changes MUST be exercised end-to-end before reporting complete.

Two paths, pick one:

### 1. Interactive verification via Playwright MCP (preferred during a task)

Use the `mcp__plugin_playwright_playwright__*` tools to drive Chromium against the running dev server.

- Ensure FE dev server runs at `http://localhost:3000` (`npm run build && npm start` in `sorento_crm_frontend/`) and BE at `http://localhost:8000`.
- **Always navigate to a feature by clicking through the sidebar / top nav from the home page — never `browser_navigate` directly to a deep URL.** Direct URL navigation hides nav-config bugs (missing entries, wrong `moduleKey`, broken permission gating, hidden behind a collapsed group). The first verification step for any new page is "open the sidebar group it belongs to and confirm the entry renders, then click it."
- Tool flow: land on `/`, `browser_snapshot` to find the relevant sidebar group button, `browser_click` to expand, then `browser_click` the leaf entry → `browser_snapshot` the destination → continue with `browser_click` / `browser_fill_form` / `browser_type` → re-snapshot to assert state.
- Always check `browser_console_messages` after the interaction. Treat unexpected `error` / `warning` as a regression.
- Use `browser_take_screenshot` for visual confirmation of CRUD flows (list → modal create → row appears → row edit → confirm-delete dialog → row gone).
- Use `browser_network_requests` to verify the FE hit the expected `/api/v1/*` endpoint with the right method/payload — confirms the hook → service → api-client chain wired correctly.
- Test the golden path AND edge cases: empty states (every section per CRUD UX standard), validation errors, delete confirmation copy, RBAC denial.
- Close with `browser_close` when done.

If unable to reach a browser (server down, sandboxed, etc.), state that explicitly. Never claim a UI change works without browser verification.

### 2. Persisted Playwright spec (when the flow deserves regression coverage)

- Specs live in `sorento_crm_frontend/e2e/`, config in `sorento_crm_frontend/playwright.config.ts` (chromium only, `baseURL` from `PORTAL_E2E_BASE_URL` ?? `http://localhost:3000`, viewport 1400x1600, single worker, no retries).
- Run all: `npm run test:e2e`. Run one: `npx playwright test e2e/foo.spec.ts`. Headed debug: `npx playwright test --headed --project=chromium`.
- Fixtures in `e2e/fixtures/` are real committed sample files (per memory rule: AI/file features test against real fixtures, not stubbed mocks). Add new fixtures alongside, do not gitignore them.
- Trace retained on failure (`trace: 'retain-on-failure'`); inspect via `npx playwright show-trace`.

### When to use which

- New CRUD page / modal / detail page → MCP interactive verification minimum; promote to a spec only when it exercises a non-trivial cross-feature flow worth pinning.
- AI / file-extraction / portal flows → spec required, real fixture required.
- Pure visual / Tailwind tweak → MCP screenshot is sufficient.

## Cache reset (frontend)

This project runs FE as a **production build** via `npm run build && npm start` — there is **no HMR**. Any FE code change requires a full rebuild before it shows up in the browser. Do not assume hot-reload.

- If FE changes don't appear: stop the server, `rm -rf sorento_crm_frontend/.next` (and optionally `node_modules/.cache`), `npm run build && npm start`, hard-refresh browser.
- `npm run dev` exists but is not how this stack is normally run; using it can hide build-time errors (e.g. server component / RSC mistakes) that only surface during `next build`.
- Playwright MCP verification flow: if the running server is `npm start`, file edits will NOT be visible until rebuild. The FE session is Claude-managed (see "Dev sessions"): kill it, `npm run build && npm start`, then verify. Only ask first if the :3000 process is one the user started themselves.

## PR checklist

`docs/PR-CHECKLIST.md` — verify CRUD pattern, delete confirmation + hard-delete semantics, empty states render, no duplication of `extractApiError` / `buildDataGridParams` / user-select helpers.

## Lessons learned (gotchas worth remembering)

- **Respond.io contact_id ≠ respond_io_id.** `PortalToken.contact_id` and the `contact_id` columns on complaints/stock_inquiries/purchase_requests store the internal `respond_contacts.id` (UUID). The Respond.io inbox URL (`/space/{space_id}/inbox/{...}`) and Respond message API need the contact's `respond_io_id`. Always resolve via `RespondContact` before building inbox URLs or calling Respond.io.
- **`respond_inbox_url` must be set at row creation** for the admin chat panel to work. Portal `_instantiate` was missing this; chat appears empty without it. Also exclude `respond_inbox_url` from any `_editable_fields` payload application.
- **Backfill scripts: idempotent JOIN-based "set to correct value where mismatch"** beats "update where NULL". The latter cannot fix prior runs that wrote wrong values; the former re-runs safely and corrects past errors.
- **Backend table names ≠ model class names.** `PurchaseRequestHeader` → table `purchase_requests`, not `purchase_request_headers`. `grep __tablename__` before writing raw SQL.
- **Hand-rolled `<table className="table-fixed">` overlaps columns** when content exceeds declared width. Always use shared `DataGrid` with explicit `size`, `tableLayout: { width: 'fixed', columnsResizable: true }`, and `truncate` + `title` for long text (see ARCHITECTURE-RULES).
- **Vitest + jsdom does not implement `scrollIntoView`.** Guard with optional chain — `ref.current?.scrollIntoView?.({...})` — so component tests don't TypeError.
- **Playwright MCP can disconnect mid-session.** No interactive browser available in that case, and the persisted-spec path requires `USER_GUIDE_E2E_EMAIL` / `PASSWORD` env vars (not in `.env*`). Component-level vitest is the autonomous fallback to verify DOM structure / classes; do not claim full UI verification from it.
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
- **sqlite pytest fixtures: pg `UUID` columns work as-is, but JSONB needs swapping and listeners need their tables.** `Base.metadata.create_all(engine, tables=[...])` with pg `UUID(as_uuid=False)` is fine (sqlite type affinity). JSONB columns (e.g. `RespondContact.session_vars`) fail DDL — swap `col.type = JSON()` and null the pg-specific `server_default` in the fixture. When the full suite runs (not the file alone), globally-registered SQLAlchemy listeners from other test modules fire on your inserts — the lookup validator queries `lookup_bindings`, so create `LookupBinding.__table__` even though your test never uses it. Mock-chain tests (`qm.filter.return_value = qm`) break silently when a query gains `.order_by()` — the auto-created child mock's `.first()` returns a truthy MagicMock instead of your sentinel.
