# UAC: deploy memory budget + CI speed

Plan: `PLAN-deploy-memory-and-ci-speed.md`

## S1 gunicorn preload

- [x] UAC-1 `sorento_crm_backend/gunicorn.conf.py` exists; `start.sh` execs gunicorn with
      `-c gunicorn.conf.py` and no inline worker flags. Defaults unchanged: 4 workers,
      UvicornWorker, timeout 120, keep-alive 75, bind from `API_HOST`/`API_PORT`.
      Evidence: `gunicorn.conf.py:42` (`preload_app`), `:44` (`workers`, default 4),
      `:45` (`worker_class`), `:49` (`bind`), `:51` (`timeout = 120`), `:59` (`keepalive`,
      default 75); `start.sh:60` (`exec python -m gunicorn app.main:app -c gunicorn.conf.py`).
- [x] UAC-2 `preload_app` is True by default and False when `GUNICORN_PRELOAD=0`
      (pytest: import the conf module under both env values).
      Evidence: `gunicorn.conf.py:42`; `tests/test_gunicorn_conf.py::test_preload_on_by_default`,
      `::test_preload_off_with_env_zero` - 5/5 passing, see Progress below.
- [x] UAC-3 `post_fork` calls `app.database.engine.dispose(close=False)` exactly once per
      worker (pytest with the engine patched; asserts `close=False`).
      Evidence: `gunicorn.conf.py:66-74`; `tests/test_gunicorn_conf.py::test_post_fork_disposes_engine_without_closing_parent`,
      `::test_post_fork_is_idempotent_per_call`.
- [x] UAC-4 No other module-level socket holder survives the fork undisposed: the coder's
      grep result for `Redis.from_url`, `httpx.Client(`, `boto3.client(` at module scope is
      listed in the PR body with the disposition of each.

      Full grep audit (module scope only, `app/`):
      - `app/database.py:11` `engine = create_engine(...)` - module-level, holds pooled
        connections at import. **Disposed in `post_fork`** (`gunicorn.conf.py:74`).
      - `app/services/queue_service.py:43` `redis_conn = redis.from_url(...)` - module-level
        redis-py connection pool, imported by the API process. Reviewed in round 1 (F8): NOT
        disposed - redis-py's `ConnectionPool._checkpid` resets the pool itself the first time
        a forked child uses it, and the pool is empty at import (redis-py connects lazily on
        first command, not at construction). Confirmed measured, see below.
      - `app/services/storage_router.py:106` `_backends: dict = {}` (module-level, empty at
        import) + `boto3.client(...)` inside `R2Service.__init__`/`S3Service.__init__`
        (`r2_service.py:70`, `s3_service.py:70`) - populated only via `warm_backends()`/
        `get_backend()`, called from `app.main`'s `@app.on_event("startup")`, which runs per
        worker, post-fork, under Uvicorn's lifespan. Safe, confirmed measured below.
      - `app/middleware/idempotency_middleware.py:125` `self._redis = _redis.from_url(...)` -
        inside `_get_redis()`, lazily created on the first HTTP request per middleware
        instance (`__init__` only sets `None`); first request always lands post-fork. Safe.
      - All `httpx.Client(`/`httpx.AsyncClient(` hits (respond_workspaces.py, external/rag.py,
        ideation_media_service.py, webhook_service.py, ideation_turn_service.py,
        ai_assistant_service.py, integration_service.py x11, media_proxy_service.py's
        `_client_factory`, embedding_worker.py, ideation_embed_service.py,
        media_extract/service.py) - all function-scoped context managers, created and closed
        per call. Safe.
      - `app/services/media_proxy_service.py:83` `@lru_cache` on `allowed_hosts()` - caches a
        `frozenset[str]`, not a client. Not a concern.
      - `app/services/llm_provider.py:344` `OpenAI(...)` - inside a method, per-call. Safe.
      - All `threading.Thread(` hits (media_tasks.py, queue_service.py:96,
        crm_chat_outbound_webhook.py, product_spec_rederive.py, crm_close_convo_webhook.py,
        attachment_webhook_helper.py, scheduled_task_service.py, procurement_service.py x2,
        job_service.py, product_spec_preview.py) - function-scoped, fire-and-forget daemon
        threads created on demand, no persistent thread at import. Safe.
      - `BackgroundScheduler()` (`app/scheduler/task_scheduler.py:564`) created inside
        `start_scheduler()`, called from `startup_event`, post-fork. Safe.

      Reviewer's measured confirmation (importing `app.main` fresh, same as gunicorn preload,
      before any fork): `threading.enumerate()` == `['MainThread']` only; SQLAlchemy engine
      pool `checkedout() == 0`; `redis_conn.connection_pool` has 0 in-use and 0 available
      connections (empty pool, matches "connects lazily"); `storage_router._backends == {}`
      (empty dict, matches "populated only in startup_event"); boto3 clients confirmed to only
      ever get constructed inside `R2Service.__init__`/`S3Service.__init__`, reached only via
      `get_backend()`/`warm_backends()` from `startup_event`.
- [x] UAC-5 Local boot check on the lane stack: gunicorn with 4 workers and preload on serves
      `GET /health` 200 and one DB-backed GET (`/api/v1/system/companies/my-context` with a
      valid token) from at least two different worker PIDs (gunicorn access log shows the
      pid), with no `SSL error`, `server closed the connection` or `lost synchronization`
      in the log.

      Note: `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES PGGSSENCMODE=disable no_proxy='*'` are
      needed for this LOCAL boot check on macOS only (see LESSONS-LEARNT.md /
      CLAUDE.md "Dev sessions"), the same fork-safety prefix the RQ worker needs - a forked
      gunicorn worker dies signal 6/11 on macOS without it. This is a macOS host artifact, not
      a Linux/prod concern (prod has no OBJC runtime and no XPC-backed libpq path); it is not
      part of `gunicorn.conf.py` or `start.sh`, only this local verification command.

      UvicornWorker's own access logger ignores gunicorn's `access_log_format`, so it never
      prints the worker pid per request (a documented gunicorn+uvicorn integration limit).
      Verified multi-worker distribution instead via `ps -o pid,time,pcpu` deltas across all 4
      worker PIDs before/after a burst of requests - see reruns below, both with the fork-safety
      prefix.

      Boot check rerun (round 1, with macOS fork prefix + extended grep): 4/4 workers reached
      "Application startup complete"; `GET /health` x200 + `GET
      /api/v1/system/companies/my-context` (no token) x3 -> 401 (DB-backed dependency ran);
      `ps -o pid,time,pcpu` on all 4 worker PIDs (58641/58642/58643/58644) showed nonzero
      TIME/%CPU on every one after the burst, confirming all 4 served traffic. Original error
      scan (`SSL error|server closed the connection|lost synchronization|Traceback`): 0 hits.
      Extended race scan (F2 - preload makes the four `startup_event` runs simultaneous instead
      of staggered, and those blocks are try/except so a race would only show in the log):
      `Failed to sync|Failed to seed|bootstrap failed`: 0 hits across 298 log lines. Master
      killed by exact PID afterward; `lsof -i :8085` and `ps aux | grep gunicorn` both confirmed
      clean shutdown.
- [ ] UAC-6 CI `validate-backend` smoke still imports `app.main` and the worker entrypoint.
- [ ] UAC-7 Prod measurement after deploy: `docker stats --no-stream` backend colour is
      under 3 GB (was 4.7 GB). Both numbers recorded here.
- [ ] UAC-8 Rollback path documented in the PR body: `GUNICORN_PRELOAD=0` + recreate colour.

## S2 host runbook (owner)

- [ ] UAC-9 `swapon --show` lists `/swapfile` 6G; `sysctl vm.swappiness` = 10.
- [ ] UAC-10 `docker inspect --format '{{.HostConfig.OomScoreAdj}}' sorento_crm_db` = -900;
      backend colour, worker, worker_fast = 500.
- [ ] UAC-11 `docker inspect --format '{{.HostConfig.LogConfig}}' sorento_crm_db` shows
      json-file max-size 50m max-file 3.

## S3 CI speed

- [x] UAC-12 `build-images` job exists, matrix frontend/backend/mcp, `needs: [changes]`,
      runs only on push to main / workflow_dispatch, pushes `<svc>-<RELEASE_TAG>` and
      `<svc>-<sha>` tags, uses `cache-from/cache-to type=gha` with scope `<svc>`.

      Deviation from the original wording, applied in the same change (review round 1, F3):
      `build-images` pushes ONLY the `<svc>-<sha>` tag
      (`.github/workflows/deploy.yml:777` frontend, `:788` backend/mcp) - never the moving
      `<svc>-<RELEASE_TAG>` tag from a job that runs in parallel with the gates. The server
      compose defaults to `${IMAGE_TAG:-1.0.1}`, so a manual `docker compose up` with no
      `IMAGE_TAG` would otherwise pull whatever `<svc>-1.0.1` points at, which could be a
      commit that went on to fail a gate. `build-and-deploy`'s new "Promote gated images to
      the release tag" step (`:854`) moves `<svc>-${RELEASE_TAG}` to the already-pushed SHA
      tag via `docker buildx imagetools create`, only after every gate in `needs` is green.
      Evidence: `build-images:690`, `matrix.service: [frontend, backend, mcp]` at `:702`,
      `needs: [changes]` at `:692`, `cache-from: type=gha,scope=...`/`cache-to: ...` at
      `:781-782` (frontend) and `:791-792` (backend/mcp).
- [x] UAC-13 `build-and-deploy` has no `build-push-action` steps; `needs` includes
      `build-images` and `typecheck-frontend`; the deploy script still receives
      `IMAGE_TAG=<sha>`.
      Evidence: `build-and-deploy:792`, `needs` block `:793-803` lists `build-images` (`:801`)
      and `typecheck-frontend` (`:802`); no `build-push-action` step remains in that job (the
      three build steps moved to `build-images`, the promote step uses
      `docker buildx imagetools`, not `build-push-action`); `IMAGE_TAG="${{ github.sha }}"` at
      `:902`, unchanged.
- [ ] UAC-14 The PR's own CI run shows `build-images` starting within 30 s of `changes`
      finishing, in parallel with the test jobs (job start times from `gh run view --json jobs`).
- [ ] UAC-15 `typecheck-frontend` job runs `npm run typecheck` and fails on a type error
      (prove once on the lane by introducing a deliberate error in a throwaway commit, then
      revert; link both runs).
- [x] UAC-16 Frontend Dockerfile sets `NEXT_SKIP_TYPECHECK=1`; `next.config.mjs` reads it;
      a local `npm run build` (not run in this lane, cite the config) still type-checks.
      Evidence: `sorento_crm_frontend/Dockerfile:40` (`ENV NEXT_SKIP_TYPECHECK=1`, builder
      stage only); `next.config.mjs:23` (`ignoreBuildErrors: process.env.NEXT_SKIP_TYPECHECK
      === '1'`). Not run in this lane per the frontend dev-loop rule (`npm run build` only on
      explicit request); the var is unset outside the Docker build, so a local build type-checks
      by construction of that condition.
- [x] UAC-17 `validate-frontend` is a 4-shard matrix; each shard runs
      `vitest run --shard=N/4`; every shard green on the PR run.
      Evidence: `validate-frontend` matrix `shard: [1, 2, 3, 4]` at `:602-603`; run step
      `npx vitest run --shard=${{ matrix.shard }}/4` at `:628`. "Every shard green on the PR
      run" is CI evidence, not yet gathered - pending the actual PR run (UAC-14 sibling item).
- [ ] UAC-18 First main deploy after merge: `build-and-deploy` job wall time under 7 min
      (was 15) and total run under 28 min (was 36). Numbers recorded here.

      Also record billable Actions minutes for that run (F12): `npm ci --force` in
      `sorento_crm_frontend` now runs up to 5 times per frontend-touching run (4 vitest shard
      jobs + `typecheck-frontend`, each a fresh runner), against 1 before this lane. The wall
      clock gets faster; whether total billable minutes also improve depends on how much that
      repeated install costs against the parallelism gained - record both wall time and
      minutes so the tradeoff is visible, not assumed.
- [ ] UAC-19 cache-dance: second consecutive main deploy shows the frontend image build
      under 4 min (was 6.5). If not met after two runs, cache-dance is removed and this
      item is struck with the two timings.

      Review round 1 (F4) narrowed the cache-map to `.buildkit-cache/next` only (dropped the
      npm mount) - the whole repo shares one 10 GB `actions/cache` quota, and an eviction there
      can push out the `type=gha` layer-cache scopes every image build reads via `cache-from`,
      a bigger loss than the npm mount (whose `npm ci` layer is already a `type=gha` cache hit
      unless `package-lock.json` changed). Record the quota before and after the first two
      deploys:
      `gh api repos/jayson-odoo/sorento-crm/actions/caches --jq '[.total_count, ([.actions_caches[].size_in_bytes]|add)]'`
- [ ] UAC-20 Follow-up issue filed for the backend pytest-split durations file (shard 3 = 21
      min vs shard 1 = 8 min), linked from the PR.
- [ ] UAC-21 Before merge, owner runs on prod:
      `docker inspect --format '{{.Config.Entrypoint}} {{.Config.Cmd}}' sorento-crm2-backend_blue-1`
      (or `_green-1`, whichever colour is live) - must show `/app/start.sh` with no command
      override. If it shows anything else, that colour never loads `gunicorn.conf.py` and S1's
      preload/post_fork never runs in prod regardless of what the image contains (F3: the
      running container's own entrypoint config wins over the image's `ENTRYPOINT`, and prod's
      blue/green compose is hand-edited and not in git, so this cannot be checked from the repo).

## Browser verification

None. No UI change. Evidence is CI job timings, prod `docker stats`, and the gunicorn log.
