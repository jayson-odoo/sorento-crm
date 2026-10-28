# Backend memory growth (BACKEND-MEMORY)

Status: investigation (2026-10-28). Track: small fix track expected (no migration, no auth/RBAC,
no ingest surface); confirmed once the fix shape is known.
Lane: `crew/backend-memory`
UAC: `backend-memory-28oct-acceptance-criteria.md` (written with the fix, once the cause is measured)

## Why

Prod `docker stats --no-stream` (owner, 28 Oct ~10:00 MYT): `backend_blue` 6.635 GiB of
15.62 GiB, db 2.87, frontend_blue 0.77, redis 0.50, worker 0.31, worker_fast 0.12, mcp 0.05.
The blue colour was started fresh by release #2 at 03:40 the same day, so it grew by 2 GB or
more in about 6 hours. Release #3 (run 40616142315) was refused by the deploy memory guard:
"4264 MB available, below DEPLOY_MIN_AVAILABLE_MB=4500" (`scripts/blue_green_deploy.sh:69`,
runbook `documentation/runbooks/memory-and-deploy-guards.md`). The preload target from
`PLAN-deploy-memory-and-ci-speed.md` was under 3 GB per colour.

Owner: no restart of the live backend (downtime). Wants to know why it grows.

## Process model (from code)

- `sorento_crm_backend/start.sh:64` runs `gunicorn app.main:app -c gunicorn.conf.py`.
- `sorento_crm_backend/gunicorn.conf.py:42` `preload_app` on, `:44` `workers = 4`,
  `:46` worker class `app.uvicorn_worker.InboxUvicornWorker`, `:58` `graceful_timeout = 150`.
  No `max_requests`, no `max_requests_jitter`, no threads setting: a worker lives as long as the
  container.
- `app/main.py:329` `startup_event` runs in EACH worker (lifespan), after the fork: it starts the
  chatbot inbox sweeper (`app/tasks/chat_turns.py:208`) and the lookup-vector warm thread
  (`app/tasks/chat_turns.py:223`), so whatever those load is private to each worker, four times.

## Steps

1. Inventory every in-process store that grows (file:line, bound, size at prod scale).
2. Measure locally (gunicorn, preload, 2 workers, dev copy `sorento_prod_1020`): RSS per process
   after warm, then after a replayed GET mix; find what grows and whether it plateaus.
3. Zero-downtime recovery command for the owner (rolling gunicorn worker recycle), with what
   users see.
4. Lasting fix as a PR: red test first, kill test, reviewer.

## Findings

(filled in as measured)
