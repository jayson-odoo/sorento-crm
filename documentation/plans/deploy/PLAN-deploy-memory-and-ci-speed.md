# Deploy memory budget + CI speed

Status: in progress (2026-09-10)
Owner: captain (Fable) / coder (Sonnet)
Lane: `feat/deploy-memory-and-ci-speed` (`.claude/worktrees/deploy-memory-ci-speed`)
UAC: `deploy-memory-and-ci-speed-acceptance-criteria.md`
Supersedes nothing. Extends `documentation/plans/ZERO-DOWNTIME-DEPLOY-PLAN.md` (implemented as
`scripts/blue_green_deploy.sh`), which assumed the host could hold two colours.

## Why (measured, 10 Sep 2026)

Deploy run 34456341559 crashed production for 2.5 minutes while reporting success.

- Host srv1250216: 4 cores, 16 GB, **no swap**. Idle with one colour: 9 GB used, 7 GB available.
- `docker stats` (one colour): backend 4.7 GB (4 gunicorn workers, no `--preload`, ~1.2 GB
  each), db 2.0 GB, frontend 0.67 GB, redis 0.53 GB, worker + worker_fast 0.3 GB.
- Blue/green overlap (step 2 to step 7 of the script) adds a second backend + frontend + mcp:
  +5.4 GB. Peak ~14.6 GB against a ~14.5 GB wall.
- 09:14:21 UTC kernel oom-killer invoked; without swap the box live-locked for 2 minutes
  (the OOM report itself took 2 minutes to print), then killed a postgres backend
  (1.4 GB shmem) at 09:16:09. Postgres terminated every server process and crash-recovered.
  dockerd, compose and the new backend colour were all frozen. n8n chat turn 15935256 timed out
  at 90 s (nginx 499); the error-logger call got 504/ECONNRESET.
- The earlier deploy the same morning (07:56) recreated the worker instantly. The box sits on
  the edge and normal app growth tipped it.
- Disk was NOT involved: 104 GB of 193 used, the chart spike was image pull + extract before
  the end-of-deploy prune. Backend image is 3.96 GB (Chromium, OpenCV, PyMuPDF, WeasyPrint).

CI timing (run 34449445835, 36 min end to end):

| Stage | Minutes |
|---|---|
| Gates in parallel: vitest 19.5, backend xdist shard 3 21.0 (shard 1 is 8.0) | 21 |
| build-and-deploy, serial: FE image 6.5, BE 2.3, MCP 0.3, server blue/green 5.0 | 15 |

The deploy job builds every image cold (no buildx, no `cache-from`, BuildKit `RUN --mount`
caches are per-runner and never exported) even though the validate jobs already built BE and
MCP with `type=gha` caches.

## Decisions (owner, 10 Sep)

- `WORKERS=4` stays. n8n and the integrations arrive in bursts; the fix is per-worker
  footprint, not worker count.
- Do: gunicorn preload (S1), host OOM hardening (S2, runbook - compose is not in git), CI
  speed (S3).
- Not now: bigger box, `WORKERS=3`, regenerating the backend pytest-split durations file
  (follow-up issue; it is the remaining critical-path item after this lane).

## Slices

### S1. gunicorn preload with a kill-switch (backend)

Simplest thing: gunicorn's own `preload_app` plus a `post_fork` hook. No new abstraction.

- New `sorento_crm_backend/gunicorn.conf.py`:
  - `preload_app = os.environ.get("GUNICORN_PRELOAD", "1") != "0"`
  - `post_fork(server, worker)`: `from app.database import engine; engine.dispose(close=False)`
    (SQLAlchemy's documented fork recipe: the child drops the parent's pooled connections
    without closing the parent's sockets). Grep `app/` for any other module-level socket
    holder (`Redis.from_url`, `httpx.Client`, boto3 clients created at import) and dispose or
    lazily recreate those in the same hook; report what was found.
  - `workers`, `worker_class`, `bind`, `timeout`, `keepalive`, logging move from `start.sh`
    into this file, read from the same env vars with the same defaults. `start.sh` becomes
    `exec python -m gunicorn app.main:app -c gunicorn.conf.py`.
- `app/main.py` startup work runs per worker after the fork (uvicorn worker lifespan), so the
  scheduler guard, audit listeners and the logging middleware are unaffected. Confirm nothing
  at import time starts a thread.
- Rollback on prod without a rebuild: `GUNICORN_PRELOAD=0` in `sorento_crm_backend/.env`,
  recreate the colour.
- Measurement is on prod (no Docker on the Mini, and macOS RSS does not show copy-on-write
  sharing): `docker stats --no-stream` on the live backend colour before and after the deploy.
  Target: backend colour under 3 GB. Record both numbers in the UAC.

### S2. Host OOM hardening (runbook, owner applies on the server)

`docker-compose.yml` is gitignored and hand-edited on the server, so this is a runbook, not a
PR. Section "Runbook" below. Items: swap file, `oom_score_adj`, json-file log rotation.

### S3. CI: hide the image builds behind the gates and cache them

Target: build-and-deploy job drops from 15 min to the ~5.5 min server step; vitest gate from
19.5 min to ~6.

a. **`build-images` job**, `needs: [changes]`, `if: push to main || workflow_dispatch`, matrix
   over `frontend | backend | mcp`, runs in parallel with every gate. `setup-buildx-action`,
   `login-action`, `build-push-action` with `push: true`, the existing two tags, and
   `cache-from: type=gha,scope=<svc>` / `cache-to: type=gha,mode=max,scope=<svc>` (the same
   scopes `validate-backend` and `validate-mcp` already warm). A SHA-tagged image for a commit
   that later fails a gate is harmless: only the deploy step pulls, and it pulls by SHA.
   `build-and-deploy` loses its three build steps and adds `build-images` to `needs`.
b. **Frontend `.next/cache` across runs**: `reproducible-containers/buildkit-cache-dance@v3`
   around the frontend build, injecting `/app/.next/cache` and `/root/.npm` from
   `actions/cache` (key on `package-lock.json` hash, restore-keys prefix). The Dockerfile's
   `RUN --mount=type=cache` lines stay as they are; cache-dance fills them. If this proves
   flaky in the first two runs, drop it and keep (a).
c. **Type-check on the runner, not in the image.** `package.json` gains
   `"typecheck": "tsc --noEmit"`. New job `typecheck-frontend` (needs changes, frontend only,
   `npm ci --force`, `npm run typecheck`), added to `build-and-deploy`'s `needs`. `next.config.mjs`
   `typescript.ignoreBuildErrors` becomes `process.env.NEXT_SKIP_TYPECHECK === '1'` and only
   the frontend Dockerfile sets `ENV NEXT_SKIP_TYPECHECK=1`, so a local `npm run build` stays
   strict. Update the comment that currently says "Keep this false".
d. **Shard vitest.** `validate-frontend` becomes a 4-way matrix running
   `npx vitest run --shard=${{ matrix.shard }}/4`. `retry: 2` stays. The `build-and-deploy`
   `needs` entry is unchanged (a matrix job is one dependency).
e. The `changes` job's `deploy.yml` path filter already forces every area on for a workflow
   edit, so this PR's own CI run exercises the new jobs.

Out of scope for this lane: the backend pytest-split durations regeneration (shard 3 at 21
min stays the critical path; file it as an issue with the numbers above).

## Runbook (S2, owner on srv1250216, root)

Swap (immediate, no restart):

```bash
fallocate -l 6G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
sysctl -w vm.swappiness=10 && echo 'vm.swappiness=10' > /etc/sysctl.d/99-swap.conf
```

Compose (`/opt/sorento-crm2/docker-compose.yml`, then `docker compose up -d` on the
touched services; the blue/green colours pick it up on the next deploy):

```yaml
x-app-logging: &app-logging
  logging:
    driver: json-file
    options: { max-size: "50m", max-file: "3" }

services:
  db:
    oom_score_adj: -900      # last to die
    <<: *app-logging
  redis:
    oom_score_adj: -500
  backend_blue:
    oom_score_adj: 500       # a gunicorn worker dies first; gunicorn respawns it
    <<: *app-logging
  backend_green:
    oom_score_adj: 500
    <<: *app-logging
  worker:
    oom_score_adj: 500
    <<: *app-logging
  worker_fast:
    oom_score_adj: 500
    <<: *app-logging
```

Mirror the same edits into the local gitignored copy so the two do not drift.

## Progress

- 2026-09-10: plan + UAC written, lane created. S1 tester writing red tests.
