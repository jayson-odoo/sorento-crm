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
echo "Running database migrations..."
# alembic upgrade head

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"

echo "Starting FastAPI server on ${API_HOST}:${API_PORT}..."
exec python -m gunicorn app.main:app \
  --workers ${WORKERS:-4} \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind "${API_HOST}:${API_PORT}" \
  --timeout 120 \
  --keep-alive 5 \
  --access-logfile - \
  --error-logfile - \
  --log-level info
