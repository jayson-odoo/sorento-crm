#!/bin/sh
set -e

# Ensure PATH includes Python user binaries
export PATH=/home/appuser/.local/bin:$PATH

# Extract database host and port from DATABASE_URL
# Format: postgresql://user:password@host:port/database
DB_HOST_PORT=$(echo "${DATABASE_URL}" | sed -n 's|.*@\([^/]*\)/.*|\1|p')
DB_HOST=$(echo "${DB_HOST_PORT}" | cut -d: -f1)
DB_PORT=$(echo "${DB_HOST_PORT}" | cut -d: -f2)

# No guessed fallback host: an empty or unparseable DATABASE_URL is a config error.
if [ -z "$DB_HOST" ]; then
  echo "DATABASE_URL is empty or has no host (expected postgresql://user:pass@host:port/db)" >&2
  exit 1
fi

echo "Waiting for database to be ready..."
echo "Connecting to database at ${DB_HOST}:${DB_PORT}..."
until pg_isready -h "${DB_HOST}" -p "${DB_PORT:-5432}" -U ${POSTGRES_USER:-postgres}; do
  echo "Database not ready, waiting..."
  sleep 2
done

echo "${DB_HOST}:${DB_PORT:-5432} - accepting connections"

# Worker entrypoint reuses this script via the `python worker.py` override; skip
# migrations there so blue/green orchestration alone owns schema upgrades and we
# don't double-run from the worker container.
if [ $# -gt 0 ]; then
  echo "Running override command: $@"
  exec "$@"
fi

# Migrations. A prod release runs `alembic upgrade head` as its own step BEFORE this container
# starts (DEPLOY-MIGRATE-STEP, scripts/blue_green_deploy.sh) and starts the colour with
# SKIP_MIGRATIONS=1, so the health wait never includes a migration and a stop can never let
# one commit after the release was reported failed. Dev, tests, CI and any box whose compose
# does not pass SKIP_MIGRATIONS through still migrate here (a no-op after the deploy step).
# Rollback also sets SKIP_MIGRATIONS=1: the older image's alembic does not know the newer head.
if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then
  echo "Running database migrations..."
  alembic upgrade head
else
  echo "SKIP_MIGRATIONS=1; skipping alembic upgrade head (the deploy's migrate step owns it)"
fi

# Post-start jobs, on EVERY start whatever SKIP_MIGRATIONS says (in prod it is always 1 now).
# Both are in the background so they never delay the health check, both are idempotent, and
# neither ever exits non-zero.
# GOODSCHAIN-INDEX-QUERY: retry any index a migration let the deploy skip when its build timed
# out (app/utils/online_index.py); a no-op once the indexes are VALID.
python -m scripts.ensure_goods_chain_indexes &
# POLH-BACKFILL-ASYNC: the PO line "first seen" history rows, out of the migration (it kept the
# 5 Nov deploy unhealthy past the 240 s wait). One commit per batch, resumable, advisory-locked;
# skips every line that already has a seen/change event (the old inline migration's rows
# included), so it inserts nothing once every linked line is seeded.
python -m scripts.backfill_po_link_seen &

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
# gunicorn.conf.py reads these from os.environ (it can't see shell argv
# substitution the way the old inline --bind flag could), so they must be
# exported even when the container never set them explicitly.
export API_HOST API_PORT

echo "Starting FastAPI server on ${API_HOST}:${API_PORT}..."
# Workers, bind, timeout, keep-alive and logging all now live in
# gunicorn.conf.py (same env vars, same defaults) alongside preload_app and
# its post_fork engine-dispose hook - see that file for the keep-alive /
# nginx upstream rationale and the preload/OOM rationale.
exec python -m gunicorn app.main:app -c gunicorn.conf.py
