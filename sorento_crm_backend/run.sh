#!/bin/bash
# Run script for FastAPI backend

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Load .env so API_HOST / API_PORT (and overrides) are visible to this shell.
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"

# Run database migrations
echo "Running database migrations..."
alembic upgrade head

# Start the server
echo "Starting FastAPI server on ${API_HOST}:${API_PORT}..."
uvicorn app.main:app --host "${API_HOST}" --port "${API_PORT}" --reload
