# Running a catalogue PDF export in a container

**Status:** the compose change below is DERIVED FROM THE CODE and has NOT been
executed. Docker was not running on 2026-08-03 and the root compose predates the
Dealer Kit entirely, so "nobody has run an export in a container yet" is still
true. This is the runbook for closing that, not a record of having closed it.

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

## What is already handled in the image

Confirmed by reading `sorento_crm_backend/Dockerfile`, not by running it:

- `playwright install-deps chromium` runs as root (system libraries).
- `USER appuser` comes BEFORE `playwright install chromium`, so the browser
  lands in `/home/appuser/.cache/ms-playwright`. This ordering is load-bearing:
  installed as root it goes to `/root/.cache`, which appuser cannot read, and
  the render fails with a missing-executable error that reads like a bad image
  rather than a permissions problem.
- The render runs in a **spawned** subprocess (`app.tasks.catalogue_render_cli`),
  never in RQ's forked work-horse. That was for a macOS segfault, and it also
  keeps Chromium's memory out of the worker in Linux.

## Verifying

```bash
# 1. Start Docker Desktop first - this is the step that blocked 2026-08-03.
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
