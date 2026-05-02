# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo layout

Monorepo. Four siblings:

- `sorento_crm_frontend/` — Next.js 15, React 19, Tailwind 4, Prisma (NextAuth + user/session DB only), Metronic 9 + ReUI shell. Calls FastAPI for all business logic.
- `sorento_crm_backend/` — FastAPI + SQLAlchemy + Alembic. All `/api/v1/*` business logic, RBAC, RQ workers, embedding pipeline.
- `sorento_crm_mcp/` — Read-only Streamable HTTP MCP server. Wraps backend GETs as MCP tools for n8n.
- `sorento_crm/` — Top-level `docker-compose.yml` + `deploy.sh` for the full stack.

Shared docs live in `docs/`. Treat `docs/ADR-PRODUCT-STANDARDS.md` and `docs/ARCHITECTURE-RULES.md` as binding.

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
npm run dev                  # Next dev (3000)
npm run build                # production
npm run build:staging        # copies .env.staging -> .env.local first
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

## Browser verification (Playwright)

Frontend changes are not done until verified in a real browser. Type-check + Vitest = code correctness, not feature correctness. UI/flow changes MUST be exercised end-to-end before reporting complete.

Two paths, pick one:

### 1. Interactive verification via Playwright MCP (preferred during a task)

Use the `mcp__plugin_playwright_playwright__*` tools to drive Chromium against the running dev server.

- Ensure FE dev server runs at `http://localhost:3000` (`npm run dev` in `sorento_crm_frontend/`) and BE at `http://localhost:8000`.
- Tool flow: `browser_navigate` → `browser_snapshot` (gets accessibility tree + element refs) → `browser_click` / `browser_fill_form` / `browser_type` → re-snapshot to assert state.
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

If FE changes don't appear: stop dev server, `rm -rf sorento_crm_frontend/.next` (and optionally `node_modules/.cache`), restart `npm run dev`, hard-refresh browser.

## PR checklist

`docs/PR-CHECKLIST.md` — verify CRUD pattern, delete confirmation + hard-delete semantics, empty states render, no duplication of `extractApiError` / `buildDataGridParams` / user-select helpers.
