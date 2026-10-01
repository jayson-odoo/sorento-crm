#!/usr/bin/env bash
# Never-stuck smoke (guard G4): boot the stack against a THROWAWAY database, seed the three
# personas, and open every app route as admin, restricted user and expired session.
# The nightly workflow (.github/workflows/never-stuck-nightly.yml) runs exactly this; a
# sandbox or laptop runs it the same way.
#
#   DATABASE_URL=postgresql://sorento:sorento@localhost:5432/sorento_smoke \
#   REDIS_URL=redis://localhost:6379/0 ./scripts/never-stuck-smoke.sh
#
# Needs: Postgres with pgvector and Redis reachable, the backend venv (or BACKEND_PYTHON)
# with requirements installed, frontend node_modules, Playwright's chromium.
# SKIP_BUILD=1 reuses an existing production build (it must have been built with
# NEVER_STUCK_API_PROXY=1, or `next start` has no /api/v1 proxy).
# Exit code is Playwright's.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BE="$ROOT/sorento_crm_backend"
FE="$ROOT/sorento_crm_frontend"
PY="${BACKEND_PYTHON:-$BE/venv/bin/python}"
BE_PORT="${NEVER_STUCK_BE_PORT:-8000}"
FE_PORT="${NEVER_STUCK_FE_PORT:-3000}"
STATE="$FE/e2e/.never-stuck"
SECRET="${JWT_SECRET:-never-stuck-smoke-secret}"

: "${DATABASE_URL:?set DATABASE_URL to a throwaway local database}"
: "${REDIS_URL:?set REDIS_URL}"
case "$DATABASE_URL" in
  *@localhost:*|*@localhost/*|*@127.0.0.1:*|*@127.0.0.1/*) ;;
  *) echo "refusing: DATABASE_URL is not a local database" >&2; exit 2 ;;
esac
export DIRECT_URL="${DIRECT_URL:-$DATABASE_URL}" JWT_SECRET="$SECRET" JWT_ALGORITHM=HS256

mkdir -p "$STATE"
pids=()
cleanup() { for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

wait_http() { # url, seconds, label
  for _ in $(seq 1 "$2"); do curl -s -o /dev/null "$1" && return 0; sleep 1; done
  echo "$3 did not answer on $1 within $2s" >&2; return 1
}

echo "== bootstrap + seed"
(cd "$BE" && "$PY" -m scripts.bootstrap_env)
(cd "$BE" && "$PY" -m scripts.seed_never_stuck_smoke --out "$STATE/seed.json" >/dev/null)

echo "== backend :$BE_PORT"
(cd "$BE" && CORS_ORIGINS="http://localhost:$FE_PORT" exec "$PY" -m uvicorn app.main:app \
  --host 127.0.0.1 --port "$BE_PORT" --workers 2) > "$STATE/backend.log" 2>&1 &
pids+=($!)
wait_http "http://127.0.0.1:$BE_PORT/docs" 120 backend

export FASTAPI_INTERNAL_URL="http://127.0.0.1:$BE_PORT" NEXTAUTH_URL="http://localhost:$FE_PORT" \
  NEXTAUTH_SECRET="$SECRET" NEXT_TELEMETRY_DISABLED=1
if [ "${SKIP_BUILD:-0}" != "1" ]; then
  echo "== frontend build"
  (cd "$FE" && NEVER_STUCK_API_PROXY=1 NEXT_SKIP_TYPECHECK=1 NODE_OPTIONS="--max-old-space-size=6144" npx next build)
fi

echo "== frontend :$FE_PORT"
(cd "$FE" && exec npx next start -p "$FE_PORT") > "$STATE/frontend.log" 2>&1 &
pids+=($!)
wait_http "http://localhost:$FE_PORT/signin" 120 frontend

echo "== smoke"
set +e
(cd "$FE" && NEVER_STUCK_SEED="$STATE/seed.json" PORTAL_E2E_BASE_URL="http://localhost:$FE_PORT" \
  npx playwright test -c playwright.never-stuck.config.ts "$@")
code=$?
set -e
(cd "$FE" && node e2e/never-stuck/summarize.mjs test-results/never-stuck/results.json) || true
exit $code
