#!/usr/bin/env bash
# Promote the warm standby (n8n box) to primary. A HUMAN runs this, AFTER fencing the old primary
# (hPanel "Stop" on the CRM box, or `docker compose stop db backend_blue backend_green worker
# worker_fast` there). Plan: documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md section 2.
#
#   ./promote-standby.sh --i-fenced-the-old-primary
#
# Steps: promote Postgres, wait until it accepts writes, start workers + scheduler (profile
# `promoted`), check the LB monitor path answers 200. Cloudflare LB then fails over by itself.
set -euo pipefail

COMPOSE="docker compose -f docker-compose.yml -f compose.standby.yml"
DB_SERVICE="${DB_SERVICE:-db}"
ROLE_URL="${ROLE_URL:-http://127.0.0.1/api/v1/health/role}"

if [ "${1:-}" != "--i-fenced-the-old-primary" ]; then
  echo "Refusing: fence the old primary first (plan section 2, Failover step 2), then pass --i-fenced-the-old-primary" >&2
  exit 2
fi

psql_db() { $COMPOSE exec -T "$DB_SERVICE" sh -c 'psql -U "$POSTGRES_USER" -d postgres -Atc "$0"' "$1"; }

if [ "$(psql_db 'SELECT pg_is_in_recovery()')" = "t" ]; then
  echo "==> Promoting ${DB_SERVICE}"
  psql_db 'SELECT pg_promote(true, 60)' >/dev/null
fi
for _ in $(seq 1 60); do
  [ "$(psql_db 'SELECT pg_is_in_recovery()')" = "f" ] && break
  sleep 1
done
if [ "$(psql_db 'SELECT pg_is_in_recovery()')" != "f" ]; then
  echo "ERROR: ${DB_SERVICE} still in recovery after 60 s; workers NOT started" >&2
  exit 1
fi
echo "==> Database is writable; starting workers + scheduler"
$COMPOSE --profile promoted up -d worker worker_fast

code=$(curl -s -o /dev/null -w '%{http_code}' "$ROLE_URL" || true)
echo "==> ${ROLE_URL} -> ${code} (expect 200; the Cloudflare LB standby pool turns healthy on its next check)"
echo "Next: n8n CRM_PRIVATE_IP flip (documentation/runbooks/n8n-private-path.md), disable the old primary's LB pool, plan failback."
