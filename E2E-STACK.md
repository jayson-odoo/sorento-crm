# SCM end-to-end integration stack

Disposable test-integration branch `fm/scm-e2e-integration-stack`. Never pushed, never a PR,
never merged anywhere. Built 2026-08-18 so the captain can test all in-flight SCM work in one
running system.

## Where it runs

| Piece | URL / location |
| --- | --- |
| Frontend | http://localhost:3050 (`npm run dev`, HMR, from this worktree) |
| Backend | http://localhost:8030 (`uvicorn app.main:app`, from this worktree; `/health` and `/docs` answer) |
| RQ worker | running from this worktree against redis db 15 (`imports, respond_io, catalogue_render, media, project_docs, flyer_read`) |
| Scratch database | `sorento_scm_e2e_stack` on localhost:5432 (a `pg_dump` / `pg_restore` copy of the dev DB `sorento_ai_automation`, real schemas only: `public`, `projects`, `scm`, `dealer_kit`) |
| Login | the `E2E_EMAIL` / `E2E_PASSWORD` pair in `sorento_crm_frontend/.env.local` |

Env changes made only in gitignored, worktree-local files: `sorento_crm_backend/.env`
(`DATABASE_URL`, `DIRECT_URL` at the scratch DB, `REDIS_URL` db 15, `CORS_ORIGINS` gains
`http://localhost:3050`) and `sorento_crm_frontend/.env.local` (Prisma at the scratch DB,
`NEXT_PUBLIC_API_URL` :8030, `NEXTAUTH_URL` :3050, cookie suffix `scme2e`). Backups of both
originals sit in this session's scratchpad. `sorento_crm_frontend/node_modules` is a symlink to
worktree 2's copy (untracked, remove before any push - which this branch never does).

Ports 8030 / 3050 were taken over from worktree 2's idle stack on the captain's instruction.

## What is in the branch

Sequential `--no-ff` merges on top of origin/main `a00a922e6`, in this order, then a merge of
the fresh origin/main (`42a61fd6a`, brings PR #215 tier-1 team-set SLA fix plus #216-#219).

| PR | Branch @ head | Result |
| --- | --- | --- |
| 204 Stage 0 + 1A | `fm/scm-stage0-1a-land` @ e637903 | conflicts (24 files): 204 predates #155's project-sales module restructure; 20 add/add files were byte-identical to the post-restructure baseline so 204's deltas were kept wholesale, `test_llm_provider_gemini.py` took main (MAX_TOKENS now raises), `worker.py` hand-merged (204's comments, main's queue order); join migration `375_merge_scm_1a_and_projects` |
| 209 Stage 1B | `fm/scm-stage1b-reconciliation` @ 5a4f3d4 | conflict: `backlog.md` only (row renumbered BL-023) |
| 214 Stage 1C | `fm/scm-stage1c-promising` @ b7f4fe7 | conflict: `test_company_scope.py` (owned count measured 110); join `376_merge_1c_supply_decisions` |
| 213 Stage 2 | `fm/scm-stage2-product-plan` @ cde6a6a | conflicts (5): `backlog.md` (BL-024), `project_so.py`, `scm/demand.py`, `test_committed_v_migration_chain.py`, `test_company_scope.py` (111). Silent collision fixed: 1C and Stage 2 each created `projects.so_supply_decisions`; 1C's model + migration own it, Stage 2's `376_scm_channel_read_model` lost its duplicate DDL and gained `depends_on = 374_so_supply_decisions`; join `378_merge_stage2_into_stack` |
| 212 proforma | `fm/scm-proforma-first-class` @ bdc73bb | conflicts (2): `backlog.md` (BL-025), `test_company_scope.py` (113). Silent break fixed: two Stage 2 fixtures in `summaryOrderMockStore.ts` lacked 212's now-required `last_incoming_currency`; join `379_merge_proforma_into_stack` |
| 211 Kailu packing list | `fm/scm-kailu-packing-list-reader` @ 4f64e92 | conflict: `scripts/bootstrap_env.py` (both 375-seed replay blocks kept, renamed by purpose); join `380_merge_kailu_into_stack` |
| 208 multi-supplier containers | `fm/scm-container-multi-supplier` @ d4fee06 | conflicts (5): `backlog.md` (BL-026), `schemas/procurement.py`, `procurement_service.py`, `scm/packing_list_service.py`, `PackingListUploadDialog.tsx`. Silent collision fixed: two `_merge_shipment_lines` definitions (208 keyed by product+supplier with `exclude_unset`, 212 with weighted-average cost) unified into one; join `381_merge_container_into_stack` |
| 207 loading plan ranking | `fm/scm-loading-plan-demand-ranking` @ 207e7ab | conflict: `allocation_suggestion_service.py` docstring only; join `382_merge_loading_plan_stack` |
| origin/main 42a61fd6a | (#215-#219) | clean, zero conflicts, no new migrations |

## Alembic

Single head: **`382_merge_loading_plan_stack`**. Proven two ways:

1. `alembic heads` prints exactly one head; `tests/test_alembic_revision_ids.py` (3) passes.
2. Empty database: `scripts/bootstrap_env.py` (the repo's from-zero path; the chain cannot
   `upgrade head` from an empty DB by design, see that script's docstring) built the schema and
   stamped `382_merge_loading_plan_stack` on scratch DB `sorento_scm_e2e_empty`.

The dev DB copy was stamped `354_projects_schema_move` but already physically carried every
table and column of all eight lanes (other lanes ran their migrations against the shared dev DB
and something restamped it). `alembic upgrade head` on the copy therefore failed at 312 with
"relation respond_contact_customers already exists". The copy was stamped to
`382_merge_loading_plan_stack` after an ORM-vs-DB check found zero missing tables and only four
missing columns on `workflow_submissions*` (a pre-existing gap in the source dev DB, unrelated
to SCM).

## Smoke

45 backend test files the eight PRs touch, run against the scratch DB:
**765 passed, 1 skipped (proforma sample gate), 0 failed.** Per-merge `tests/scm` differential
runs (baseline vs merged, same DB) showed zero new failures at every step; the 55 failures seen
on both sides are the known local-DB / env artifacts.

Browser (agent-browser, headless): signin page loads, login succeeds against the scratch DB,
sidebar shows Supply Chain / Procurement / Project Sales groups, `Supply Chain -> Loading Plan`
renders (empty state, supplier picker), `Supply Chain -> Incoming Containers` renders 15 real
containers from the copied data including the Kailu preload; `/api/v1/scm/inbound-shipments`
200, no page errors.

## Known limitations / open items

- Frontend is a dev (HMR) server, not a prod build, so the captain could test immediately.
- `sorento_crm_mcp` is not installed in the shared venv: backend logs
  "Failed to sync MCP tool catalog at startup" (non-fatal); the MCP suite for #217 was not run.
- `app/(protected)/scm/lib/format.guard.test.ts` is red on PR 213's own `reorder/lib/qtyPrecision.ts:74`
  (pre-existing on 213, untouched here).
- Stage 2's extra columns on `so_supply_decisions` (`updated_at`, state CHECK, `confirmed_at NOT NULL`)
  did not survive; nothing in the merged tree reads them.
- BL-025 (packing-list cost wipe on edit) looks fixed by 208's `_upsert_shipment_lines` but the
  row is still open and the cost/currency case is not pinned by a test.
- Unratified config riding in from the PRs: `sorento_crm_backend/AGENTS.md` + `CLAUDE.md`
  symlink (204), two root `CLAUDE.md` lessons (208).
- Machine hazard: a previous stack on :3050/:8030 was SIGTERMed under memory pressure. If this
  one dies, restart from this worktree with the env files as they are (no re-merge needed).

No feature pair could not be made to work together.
