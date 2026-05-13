# Zero-downtime deploy plan (blue/green behind nginx)

Status: draft. Captured 2026-05-13 — not yet implemented.

## Current state

- Build pre-pushed to Docker Hub by `.github/workflows/deploy.yml`.
- Server runs `git pull` then `docker compose up -d --remove-orphans --force-recreate`.
- Everything (db, backend, frontend, mcp) recreated each deploy → ~30s 502 window.
- Migrations run inside backend entrypoint (`alembic upgrade head` before gunicorn binds).
- Nginx already in front as reverse proxy on the host.
- Keep `alembic upgrade head` inside backend entrypoint (per ops preference).
- Always-recreate-all is fine; FE rebuild always required.

## Goal

Drop downtime to ~0s. End-user sees no 502 during deploy.

## Approach: blue/green per service, swap upstream in nginx

Two compose instances per service (`backend_blue` / `backend_green`, same for frontend + mcp).
At any time, exactly one color receives traffic via nginx upstream. Deploy = start the other
color, wait for healthcheck green, atomically swap the nginx upstream file, `nginx -s reload`
(graceful — in-flight requests survive), then stop the old color.

DB is **not** part of blue/green. Single postgres container, untouched on deploy.

### Compose sketch

```yaml
services:
  backend_blue:
    image: ${IMAGE_REPO}:backend-${TAG}
    environment: { ... }                    # unchanged from today
    networks: [sorento_network]
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/health"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 30s                     # covers alembic time
    restart: unless-stopped
    # entrypoint keeps `alembic upgrade head`

  backend_green:
    # identical to backend_blue
    profiles: ["green"]                     # only started when activated

  frontend_blue: { ... }
  frontend_green: { profiles: ["green"], ... }
  mcp_blue:      { ... }
  mcp_green:     { profiles: ["green"], ... }
```

Drop `ports:` on backend / frontend / mcp. Only nginx publishes 80/443. Nginx must share
`sorento_network` (run nginx itself as a compose service, or attach with `--network`).

### Nginx upstreams (rendered file the deploy script edits)

`/etc/nginx/conf.d/sorento_upstreams.conf`:

```nginx
upstream backend  { server backend_blue:8000;  keepalive 32; }
upstream frontend { server frontend_blue:80;   keepalive 32; }
upstream mcp      { server mcp_blue:8765;      keepalive 16; }
```

Server blocks: `proxy_pass http://backend;` (or `frontend` / `mcp`).

### Deploy script (replaces full-recreate path on the server)

```bash
set -e
cd /opt/sorento-crm2
ACTIVE=$(cat .active_color 2>/dev/null || echo blue)
[ "$ACTIVE" = "blue" ] && { NEW=green; OLD=blue; } || { NEW=blue; OLD=green; }

# pull + retag (as today)
docker pull "$IMAGE_REPO:backend-$SHA_TAG"
docker pull "$IMAGE_REPO:frontend-$SHA_TAG"
docker pull "$IMAGE_REPO:mcp-$SHA_TAG"
docker tag  "$IMAGE_REPO:backend-$SHA_TAG"  "$IMAGE_REPO:backend-$TAG"
docker tag  "$IMAGE_REPO:frontend-$SHA_TAG" "$IMAGE_REPO:frontend-$TAG"
docker tag  "$IMAGE_REPO:mcp-$SHA_TAG"      "$IMAGE_REPO:mcp-$TAG"

# bring up NEW color (alembic runs inside backend_$NEW; blue keeps serving)
docker compose --profile $NEW up -d backend_$NEW frontend_$NEW mcp_$NEW

# wait healthy (up to ~2 min)
for svc in backend frontend mcp; do
  cid="sorento_${svc}_${NEW}"
  for i in $(seq 1 60); do
    s=$(docker inspect --format='{{.State.Health.Status}}' "$cid" 2>/dev/null || echo starting)
    [ "$s" = "healthy" ] && break
    sleep 2
  done
  [ "$s" = "healthy" ] || { echo "$cid not healthy, aborting"; exit 1; }
done

# atomic swap of upstreams
sed -i \
  -e "s/backend_${OLD}:8000/backend_${NEW}:8000/" \
  -e "s/frontend_${OLD}:80/frontend_${NEW}:80/" \
  -e "s/mcp_${OLD}:8765/mcp_${NEW}:8765/" \
  /etc/nginx/conf.d/sorento_upstreams.conf

nginx -t && nginx -s reload                  # graceful, no dropped sockets

# drain + stop OLD
sleep 10
docker compose stop backend_$OLD frontend_$OLD mcp_$OLD
docker compose rm -f backend_$OLD frontend_$OLD mcp_$OLD

echo $NEW > .active_color
docker system prune -f
```

## Gotchas to design around before flipping this on

1. **Migrations must be backwards compatible at swap time.** Blue keeps serving while
   green runs `alembic upgrade head`. Drop / rename column will crash blue mid-deploy.
   Operating rule: additive migrations only on the deploy that ships new code; deferred
   destructive migration in a follow-up deploy after old code is fully drained.
2. **WebSocket / SSE drain.** AI assistant streaming + Respond.io chat panel may hold
   long-lived connections. Add `proxy_http_version 1.1; proxy_set_header Connection "";
   proxy_read_timeout 1h;` in nginx and lengthen the post-swap `sleep` so existing
   sockets close gracefully. Alternative: graceful shutdown signal to old backend.
3. **DB connection pool doubles briefly.** Two backend instances overlap during swap.
   Bump `max_connections` (or use pgbouncer) if currently tight.
4. **RQ worker + scheduler.** If background workers live in the backend container,
   running both colors = double processing of queued jobs and cron ticks. Either:
   - move RQ worker + scheduler to a separate service that is NOT blue/green (recreate
     in place, accept its tiny restart window), or
   - guard scheduled jobs with a leader election / distributed lock.
5. **`/health` semantics.** Endpoint must return 200 only AFTER alembic + DB ping succeed,
   not just "process up." Otherwise we swap onto a not-actually-ready container.
6. **First boot.** `.active_color` won't exist; default to `blue` and assume the live
   nginx config already points at `backend_blue` etc.
7. **Static asset cache busting (frontend).** Next.js hashed assets are fine, but `_next`
   chunks served by old container disappear when it stops. Drain with `sleep` longer than
   the longest page-load TTI, or keep both colors warm for a few minutes.
8. **CI workflow change.** `.github/workflows/deploy.yml` deploy step rewritten to run the
   blue/green script above instead of `docker compose up -d --force-recreate`.

## Open questions (decide before implementing)

- Run nginx inside compose, or keep it on the host? If host, nginx must reach docker
  network — either expose backend on a stable host port per color, or use a docker
  network plugin / `--network`.
- Per-color container names vs. compose project rename pattern? `container_name:
  sorento_backend_blue` is simplest but blocks `docker compose up` of the same service
  with a different name. Likely easier to drop `container_name:` and let compose name
  them by service.
- How long is the safe drain window for SSE in this app? Need data before committing
  to a fixed `sleep`.

## Quick wins still worth doing even before blue/green

Even if blue/green slips, these reduce downtime:

- Add real `/health`-based healthchecks on backend + frontend (compose `healthcheck:`).
- Pre-build + push in CI is already done — keep it.
- Stop including `db` in the recreated set (omit `--force-recreate` for db service).
- Run `docker system prune` AFTER healthchecks confirm green, not during.
