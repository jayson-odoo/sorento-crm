#!/bin/sh
set -e

# Ensure PATH includes Python user binaries
export PATH=/home/appuser/.local/bin:$PATH

echo "Waiting for database to be ready..."
until pg_isready -h db -U ${POSTGRES_USER:-postgres}; do
  echo "Database not ready, waiting..."
  sleep 2
done

echo "db:5432 - accepting connections"
echo "Running database migrations..."
alembic upgrade head

echo "Starting FastAPI server..."
exec python -m gunicorn app.main:app \
  --workers ${WORKERS:-4} \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --keep-alive 5 \
  --access-logfile - \
  --error-logfile - \
  --log-level info
