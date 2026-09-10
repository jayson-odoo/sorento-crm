# UAC: deploy memory budget + CI speed

Plan: `PLAN-deploy-memory-and-ci-speed.md`

## S1 gunicorn preload

- [ ] UAC-1 `sorento_crm_backend/gunicorn.conf.py` exists; `start.sh` execs gunicorn with
      `-c gunicorn.conf.py` and no inline worker flags. Defaults unchanged: 4 workers,
      UvicornWorker, timeout 120, keep-alive 75, bind from `API_HOST`/`API_PORT`.
- [ ] UAC-2 `preload_app` is True by default and False when `GUNICORN_PRELOAD=0`
      (pytest: import the conf module under both env values).
- [ ] UAC-3 `post_fork` calls `app.database.engine.dispose(close=False)` exactly once per
      worker (pytest with the engine patched; asserts `close=False`).
- [ ] UAC-4 No other module-level socket holder survives the fork undisposed: the coder's
      grep result for `Redis.from_url`, `httpx.Client(`, `boto3.client(` at module scope is
      listed in the PR body with the disposition of each.
- [ ] UAC-5 Local boot check on the lane stack: gunicorn with 4 workers and preload on serves
      `GET /health` 200 and one DB-backed GET (`/api/v1/system/companies/my-context` with a
      valid token) from at least two different worker PIDs (gunicorn access log shows the
      pid), with no `SSL error`, `server closed the connection` or `lost synchronization`
      in the log.
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

- [ ] UAC-12 `build-images` job exists, matrix frontend/backend/mcp, `needs: [changes]`,
      runs only on push to main / workflow_dispatch, pushes `<svc>-<RELEASE_TAG>` and
      `<svc>-<sha>` tags, uses `cache-from/cache-to type=gha` with scope `<svc>`.
- [ ] UAC-13 `build-and-deploy` has no `build-push-action` steps; `needs` includes
      `build-images` and `typecheck-frontend`; the deploy script still receives
      `IMAGE_TAG=<sha>`.
- [ ] UAC-14 The PR's own CI run shows `build-images` starting within 30 s of `changes`
      finishing, in parallel with the test jobs (job start times from `gh run view --json jobs`).
- [ ] UAC-15 `typecheck-frontend` job runs `npm run typecheck` and fails on a type error
      (prove once on the lane by introducing a deliberate error in a throwaway commit, then
      revert; link both runs).
- [ ] UAC-16 Frontend Dockerfile sets `NEXT_SKIP_TYPECHECK=1`; `next.config.mjs` reads it;
      a local `npm run build` (not run in this lane, cite the config) still type-checks.
- [ ] UAC-17 `validate-frontend` is a 4-shard matrix; each shard runs
      `vitest run --shard=N/4`; every shard green on the PR run.
- [ ] UAC-18 First main deploy after merge: `build-and-deploy` job wall time under 7 min
      (was 15) and total run under 28 min (was 36). Numbers recorded here.
- [ ] UAC-19 cache-dance: second consecutive main deploy shows the frontend image build
      under 4 min (was 6.5). If not met after two runs, cache-dance is removed and this
      item is struck with the two timings.
- [ ] UAC-20 Follow-up issue filed for the backend pytest-split durations file (shard 3 = 21
      min vs shard 1 = 8 min), linked from the PR.

## Browser verification

None. No UI change. Evidence is CI job timings, prod `docker stats`, and the gunicorn log.
