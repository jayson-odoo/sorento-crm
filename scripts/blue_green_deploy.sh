#!/usr/bin/env bash
# Blue/green orchestration. Run from the server checkout containing docker-compose.yml.
#
# Public endpoints stay stable across deploys:
#   n8n  -> http://72.62.195.20:8765/mcp                (host nginx -> sorento_mcp upstream)
#   API  -> https://fe-sorento.foundryx.my/api/v1/*     (host nginx -> sorento_backend upstream)
#   UI   -> https://fe-sorento.foundryx.my/             (host nginx -> sorento_frontend upstream)
#
# Container loopback ports alternate per color:
#   blue:  backend 127.0.0.1:8000 | frontend 127.0.0.1:3000 | mcp 127.0.0.1:8766
#   green: backend 127.0.0.1:8010 | frontend 127.0.0.1:3010 | mcp 127.0.0.1:8776
#
# Required env: IMAGE_TAG (git SHA, set by CI).
# Tracks active color in .active_color (default blue on first run).

set -euo pipefail

cd "$(dirname "$0")/.."   # repo root containing docker-compose.yml
: "${IMAGE_TAG:?must be set to the git SHA pushed by CI}"
export IMAGE_TAG

UPSTREAMS_FILE="/etc/nginx/conf.d/sorento_upstreams.conf"
DRAIN_SECONDS="${DRAIN_SECONDS:-30}"
HEALTH_WAIT_TICKS="${HEALTH_WAIT_TICKS:-120}"   # 120 * 2s = 4 min max
TICK_SECONDS=2

ACTIVE=$(cat .active_color 2>/dev/null || echo blue)
if [ "$ACTIVE" = "blue" ]; then
  NEW=green; OLD=blue
  NEW_BE_PORT=8010; NEW_FE_PORT=3010; NEW_MCP_PORT=8776
else
  NEW=blue;  OLD=green
  NEW_BE_PORT=8000; NEW_FE_PORT=3000; NEW_MCP_PORT=8766
fi

echo "==> Active=${ACTIVE} New=${NEW} IMAGE_TAG=${IMAGE_TAG}"

# 1. Pull new images (SHA-tagged) + worker (uses backend image)
echo "==> Pulling images"
docker compose --profile "${NEW}" pull "backend_${NEW}" "frontend_${NEW}" "mcp_${NEW}"
docker compose pull worker

# 2. Bring up new color. start.sh runs `alembic upgrade head` before gunicorn
#    so the new container only goes healthy after schema is at HEAD. If alembic
#    fails the container exits → healthcheck fails → this script aborts at
#    step 3 and OLD color keeps serving traffic. Set SKIP_MIGRATIONS=1 in
#    backend env for manual two-phase (expand-contract) rollouts.
echo "==> Starting ${NEW} color"
docker compose --profile "${NEW}" up -d --no-deps \
  "backend_${NEW}" "frontend_${NEW}" "mcp_${NEW}"

# 3. Wait for all three new containers to be healthy
echo "==> Waiting for healthchecks"
for svc in backend frontend mcp; do
  cid=$(docker compose ps -q "${svc}_${NEW}")
  if [ -z "$cid" ]; then
    echo "ERROR: container ${svc}_${NEW} not found"; exit 1
  fi
  i=0
  while [ $i -lt $HEALTH_WAIT_TICKS ]; do
    state=$(docker inspect --format='{{.State.Health.Status}}' "$cid" 2>/dev/null || echo starting)
    if [ "$state" = "healthy" ]; then
      echo "    ${svc}_${NEW} healthy after $((i * TICK_SECONDS))s"
      break
    fi
    sleep $TICK_SECONDS
    i=$((i + 1))
  done
  if [ "$state" != "healthy" ]; then
    echo "ERROR: ${svc}_${NEW} not healthy after $((HEALTH_WAIT_TICKS * TICK_SECONDS))s"
    docker compose logs --tail=200 "${svc}_${NEW}" || true
    exit 1
  fi
done

# 4. Atomic upstream swap + graceful nginx reload
echo "==> Swapping nginx upstreams to ${NEW}"
TMP_UPSTREAM=$(mktemp)
cat > "$TMP_UPSTREAM" <<EOF
upstream sorento_backend  { server 127.0.0.1:${NEW_BE_PORT};  keepalive 32; }
upstream sorento_frontend { server 127.0.0.1:${NEW_FE_PORT};  keepalive 32; }
upstream sorento_mcp      { server 127.0.0.1:${NEW_MCP_PORT}; keepalive 16; }
EOF
sudo install -m 0644 "$TMP_UPSTREAM" "$UPSTREAMS_FILE"
rm -f "$TMP_UPSTREAM"
sudo nginx -t
sudo nginx -s reload

# 5. Drain — let nginx finish in-flight requests on OLD color
echo "==> Draining ${DRAIN_SECONDS}s"
sleep "$DRAIN_SECONDS"

# 6. Recreate worker on new image (small background-job blip; safe — RQ pulls atomically)
echo "==> Recreating worker on new image"
docker compose up -d --force-recreate --no-deps worker

# 7. Stop and remove old color (tolerate first-deploy where OLD doesn't exist)
echo "==> Stopping ${OLD} color"
docker compose stop "backend_${OLD}" "frontend_${OLD}" "mcp_${OLD}" || true
docker compose rm -f "backend_${OLD}" "frontend_${OLD}" "mcp_${OLD}" || true

# 8. Persist new active color, clean up
echo "${NEW}" > .active_color
docker image prune -f >/dev/null || true

echo "==> Deploy complete. Active=${NEW}"
