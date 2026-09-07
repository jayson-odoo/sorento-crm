#!/bin/sh
set -e

# Ensure PATH includes Python user binaries
export PATH=/home/appuser/.local/bin:$PATH

# Extract database host and port from DATABASE_URL
# Format: postgresql://user:password@host:port/database
DB_HOST_PORT=$(echo "${DATABASE_URL}" | sed -n 's|.*@\([^/]*\)/.*|\1|p')
DB_HOST=$(echo "${DB_HOST_PORT}" | cut -d: -f1)
DB_PORT=$(echo "${DB_HOST_PORT}" | cut -d: -f2)

# Default to host:port if not found in DATABASE_URL
if [ -z "$DB_HOST" ]; then
  DB_HOST="72.62.195.19"
  DB_PORT="5432"
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

# Run migrations before serving. Alembic uses `alembic_version` + an advisory
# lock, so concurrent blue/green starts are safe (the loser no-ops). Failure
# here aborts the container start → healthcheck fails → blue/green swap aborts
# → old color keeps serving. Set SKIP_MIGRATIONS=1 to bypass when manually
# managing migrations (e.g. expand-contract two-phase rollouts).
if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then
  echo "Running database migrations..."
  alembic upgrade head
else
  echo "SKIP_MIGRATIONS=1; skipping alembic upgrade head"
fi

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"

echo "Starting FastAPI server on ${API_HOST}:${API_PORT}..."
# --keep-alive must be LONGER than the host nginx's upstream keepalive (its
# keepalive_timeout, default 60s / 75s). With 5s gunicorn closed idle upstream
# connections that nginx still considered open, and the next request on that
# socket died as an intermittent 502 "upstream prematurely closed connection"
# - about 1 in 25 of the ESB's 14s ingest batches on production, 2026-09-07,
# which their all-or-nothing push then amplified into a 5x re-offer rate.
exec python -m gunicorn app.main:app \
  --workers ${WORKERS:-4} \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind "${API_HOST}:${API_PORT}" \
  --timeout 120 \
  --keep-alive "${GUNICORN_KEEP_ALIVE:-75}" \
  --access-logfile - \
  --error-logfile - \
  --log-level info
