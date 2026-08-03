# Running a catalogue PDF export in a container

**Status: still not executed, but the diagnosis is now VERIFIED rather than
derived.** Docker was started on 2026-08-03 and `docker compose --profile blue
config` was resolved. It confirms every claim below against the resolver rather
than against a reading of the YAML:

| Service | `sorento_network` alias | `DEALER_KIT_PRINT_BASE_URL` |
|---|---|---|
| `backend_blue` | `backend` | unset |
| `mcp_blue` | `mcp` | unset |
| `frontend_blue` | **none** | unset |
| `worker` | none (does not need one) | **unset** |

So the two changes below are exactly the two that are missing, and nothing else
is.

**Why it still was not run** is a different blocker from the original one, and
a more interesting one. See "What stops `up` on this machine".

Compose is deliberately not in the repo (`docker-compose.yml` at the
`sorento_crm/` root is gitignored, and CI ships only the deploy script), so the
YAML here is a snippet to paste rather than a file to merge.

---

## The blocker, which is a real one

`generate_catalogue_pdf` renders by pointing headless Chromium at the FRONTEND:

```
{DEALER_KIT_PRINT_BASE_URL}/c/print/{download_id}?token={token}
```

with `DEALER_KIT_PRINT_BASE_URL` defaulting to `http://localhost:3000`. Inside a
container `localhost` is the worker itself, so unset it renders nothing and the
export dies on a 60s ready-timeout.

The obvious fix - point it at the frontend service - **does not work today**:

- `backend` and `mcp` each declare a `sorento_network` alias, so the active
  blue/green colour answers to a stable name.
- **The frontend declares no alias.** The services are `frontend_blue` and
  `frontend_green` under mutually exclusive profiles, so there is no hostname
  that resolves to whichever is running. Hardcoding `frontend_blue` breaks every
  green deploy, silently, and only for PDF export.

So the frontend needs the same alias treatment the other two already have.

## The compose change

**1. Give the frontend a stable alias.** In `x-frontend-base`, replace:

```yaml
  networks:
    - sorento_network
```

with:

```yaml
  networks:
    sorento_network:
      aliases:
        - frontend
```

This mirrors `x-backend-base` and `x-mcp-base` exactly. Only one colour runs at
a time, so the alias is unambiguous.

**2. Tell the worker where the frontend is.** In the `worker` service's
`environment` block, beside `ENABLE_SCHEDULER: "true"`:

```yaml
      DEALER_KIT_PRINT_BASE_URL: "http://frontend:3000"
```

The internal port is 3000 for both colours (green only differs in its published
host port), so the alias plus 3000 is correct either way.

Nothing else changes. `worker.py` already listens on `catalogue_render`
alongside `imports` and `respond_io`, and the queue is separate on purpose so a
slow Chromium render cannot block an Excel import.

## The image does not exist on main yet

**Compose builds `context: ./sorento_crm_backend` of the CHECKOUT, and the
Playwright steps live only on `feat/dealer-kit-hardening`.** Verified on
2026-08-03 by building `worker` from the main checkout and looking inside:

```
$ docker run --rm --entrypoint sh jayson1004/sorento-crm:backend-1.0.1 -c \
    'python -c "import playwright"'
ModuleNotFoundError: No module named 'playwright'
```

`grep -n playwright sorento_crm_backend/Dockerfile` returns nothing on main and
four lines on this branch. So `docker compose up --build worker` against main
produces a worker that cannot render at all, and the failure looks like a
render timeout rather than a missing dependency.

That means the container export cannot be verified from the deployed compose
until this branch merges. Until then, build the worker image from the branch
checkout explicitly:

```bash
docker build -t sorento-crm:dealer-kit-worker-test \
  .claude/worktrees/dealer-kit/sorento_crm_backend
```

and point the compose `worker` service at that tag for the test.

## What is already handled in the image

Read off this branch's `sorento_crm_backend/Dockerfile`:

- `playwright install-deps chromium` runs as root (system libraries).
- `USER appuser` comes BEFORE `playwright install chromium`, so the browser
  lands in `/home/appuser/.cache/ms-playwright`. This ordering is load-bearing:
  installed as root it goes to `/root/.cache`, which appuser cannot read, and
  the render fails with a missing-executable error that reads like a bad image
  rather than a permissions problem.
- The render runs in a **spawned** subprocess (`app.tasks.catalogue_render_cli`),
  never in RQ's forked work-horse. That was for a macOS segfault, and it also
  keeps Chromium's memory out of the worker in Linux.

## What stops `up` on this machine

Two things, and neither is about the Dealer Kit.

**1. Every infrastructure port is already taken by the local dev stack.**
Checked on 2026-08-03 with `lsof -sTCP:LISTEN`:

| Compose service | Host bind | Already held by |
|---|---|---|
| `db` | `5432` | local Postgres (the prod-copy dev DB) |
| `redis` | `6379` | local Redis |
| `frontend_blue` | `127.0.0.1:3000` | a local `node` process |

`docker compose up` fails on the bind. It does NOT clobber them, but it does
not start either. Run it with a `docker-compose.override.yml` that remaps those
three host ports, or stop the local services first - **your call which**, since
stopping them takes the dev stack down with them.

**2. The worker container runs the scheduler with live credentials.**
`ENABLE_SCHEDULER: "true"` is set on `worker` (correctly - it is the single
instance that owns cron ticks). Its `env_file` is the real
`sorento_crm_backend/.env`, which carries a production `N8N_WEBHOOK_URL` and a
production `RESPOND_API_KEY`. The database it talks to is the CONTAINERISED one
(`pgbouncer` / `db`, not `localhost`), but the `sorento_crm_postgres_data`
volume already exists on this machine and its contents were not inspected.

If that volume holds real rows, bringing the worker up fires SLA escalations and
Respond.io sends against production endpoints. **Before running this, either
set `ENABLE_SCHEDULER: "false"` on the worker for the duration of the test (the
export queue drains without the scheduler - it is RQ, not cron), or point
`env_file` at a scratch env with the outbound credentials blanked.**

That was the reason this was not executed unattended on 2026-08-03, and it is a
better reason than "Docker was off".

## Verifying

```bash
# 1. Deal with both blockers above first. Docker itself is no longer the issue.
docker compose up -d --build worker frontend_blue backend_blue redis db

# 2. Confirm the browser is where the worker will look for it.
docker compose exec worker ls /home/appuser/.cache/ms-playwright

# 3. Confirm the worker can actually reach the frontend by its new alias.
docker compose exec worker python -c \
  "import urllib.request;print(urllib.request.urlopen('http://frontend:3000/').status)"

# 4. Trigger an export from the UI (Dealer Kit -> Catalogue Pages -> a published
#    page -> Export PDF), then watch it drain.
docker compose logs -f worker
```

**Done means:** a PDF lands in `user_downloads`, opens, and matches what the
same page exports locally. A render that times out at 60s is almost always step
3 failing - check the alias before anything else.

## Also still unproven

The export snapshots its render context at ENQUEUE (`dealer_kit.export_request`,
migration 311) and a worker with no snapshot REFUSES rather than falling back to
a system principal, because that principal is a STAFF principal and would print
internal prices into a consumer's document. That refusal path has unit coverage
but has never been exercised in a container either. Worth doing in the same
sitting: enqueue an export, delete its `export_request` row before the worker
picks it up, and confirm it refuses rather than renders.
