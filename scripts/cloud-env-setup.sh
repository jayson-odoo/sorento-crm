#!/usr/bin/env bash
# Bootstrap a Claude Code CLOUD lane (code.claude.com managed VM) so it can run
# the backend pytest suite and the frontend vitest suite against a real,
# empty, seeded Postgres - exactly the substrate
# `.github/workflows/deploy.yml`'s `test-backend` / `validate-frontend` jobs
# use, not sqlite (LESSONS-LEARNT.md: "Tests run on Postgres ONLY").
#
# Reference: .github/workflows/deploy.yml lines ~495-600 (backend job) and
# ~719-758 (frontend job). This script reproduces that job's setup on a
# single always-on VM instead of a fresh container per run, so it detects
# existing state and skips what is already done (idempotent, safe to rerun).
#
# TIMING: the managed VM's setup script has a 5-minute cap and its result is
# cached. `pip install -r requirements.txt` and `npm ci --force` can each take
# longer than that alone on a cold VM. If the cloud session's first prompt
# reports the setup script timed out, just ask it to run this script again
# (`bash scripts/cloud-env-setup.sh`) from the prompt - venv/node_modules
# survive a timed-out setup run and pick up where they left off.
#
# Usage:
#   bash scripts/cloud-env-setup.sh              # do the setup
#   bash scripts/cloud-env-setup.sh --dry-run     # print every command, do nothing
#   bash scripts/cloud-env-setup.sh --check       # verify the resulting state only
set -euo pipefail

DRY_RUN=0
CHECK=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --check) CHECK=1 ;;
    -h|--help)
      sed -n '2,23p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "usage: $0 [--dry-run|--check]" >&2
      exit 2
      ;;
  esac
done

if [ "$DRY_RUN" -eq 1 ] && [ "$CHECK" -eq 1 ]; then
  echo "--dry-run and --check are mutually exclusive" >&2
  exit 2
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
BACKEND_DIR="$REPO_ROOT/sorento_crm_backend"
FRONTEND_DIR="$REPO_ROOT/sorento_crm_frontend"
MCP_DIR="$REPO_ROOT/sorento_crm_mcp"
VENV_DIR="$BACKEND_DIR/venv"
VENV_PY="$VENV_DIR/bin/python"
ENV_FILE="$BACKEND_DIR/.env.ci-tests"

# Same values as the backend CI job's `env:` block (deploy.yml ~line 542), so
# behaviour matches the deploy gate rather than diverging on a throwaway lane.
DB_USER=sorento
DB_PASSWORD=sorento
DB_NAME=sorento_ci
DB_HOST=localhost
DB_PORT=5432
DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
REDIS_URL="redis://localhost:6379/0"
JWT_SECRET="ci-dummy-secret"
JWT_ALGORITHM="HS256"
# Throwaway key for a lane that never talks to a real external caller; lets a
# cloud coder/tester exercise EXTERNAL_API_KEY-gated routes without inventing
# one by hand. EXTERNAL_API_KEY_ACT_AS_USER_ID is deliberately left unset: a
# freshly bootstrapped database has no `users` rows (bootstrap_env seeds
# reference data - roles, order statuses, permissions - not accounts), so
# there is no real user id to point it at yet.
EXTERNAL_API_KEY="cloud-lane-test-key"

log() { echo "[cloud-env-setup] $*"; }

# Prints the command, and - unless this is a dry run - executes it. The single
# choke point that makes --dry-run "print every command it would run" true by
# construction instead of by two copies of the same logic drifting apart.
run() {
  echo "+ $*"
  if [ "$DRY_RUN" -eq 0 ]; then
    "$@"
  fi
}

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
fi

# ---------------------------------------------------------------------------
# --check: verify state only, touch nothing, exit non-zero listing gaps.
# ---------------------------------------------------------------------------
if [ "$CHECK" -eq 1 ]; then
  missing=()

  if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1; then
    missing+=("postgres not accepting connections (pg_isready failed)")
  fi

  if ! PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT 1" >/dev/null 2>&1; then
    missing+=("cannot SELECT 1 as $DB_USER against $DB_NAME")
  fi

  if ! PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT 1 FROM pg_extension WHERE extname='vector'" 2>/dev/null | grep -q 1; then
    missing+=("vector extension not installed in $DB_NAME")
  fi

  if [ -x "$VENV_DIR/bin/alembic" ]; then
    current="$(cd "$BACKEND_DIR" && SORENTO_ENV_FILE=.env.ci-tests "$VENV_DIR/bin/alembic" current 2>/dev/null | awk '{print $1}')"
    head="$(cd "$BACKEND_DIR" && SORENTO_ENV_FILE=.env.ci-tests "$VENV_DIR/bin/alembic" heads 2>/dev/null | awk '{print $1}')"
    if [ -z "$current" ] || [ "$current" != "$head" ]; then
      missing+=("alembic not at head (current='${current:-<none>}' head='${head:-<unknown>}')")
    fi
  else
    missing+=("backend venv/alembic not installed")
  fi

  if ! redis-cli ping 2>/dev/null | grep -q PONG; then
    missing+=("redis not responding to PING")
  fi

  if [ ! -d "$FRONTEND_DIR/node_modules" ] || [ -z "$(ls -A "$FRONTEND_DIR/node_modules" 2>/dev/null)" ]; then
    missing+=("frontend node_modules missing")
  fi

  if [ "${#missing[@]}" -eq 0 ]; then
    log "all checks passed"
    exit 0
  fi

  log "missing:"
  for item in "${missing[@]}"; do
    echo "  - $item"
  done
  exit 1
fi

# ---------------------------------------------------------------------------
# Setup (also the command list --dry-run prints).
# ---------------------------------------------------------------------------

log "starting postgresql + redis"
run $SUDO service postgresql start
run $SUDO service redis-server start

log "ensuring role '$DB_USER' and database '$DB_NAME' exist"
if [ "$DRY_RUN" -eq 0 ] && sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" 2>/dev/null | grep -q 1; then
  log "role $DB_USER already exists, skipping create"
else
  run sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE ROLE $DB_USER LOGIN SUPERUSER PASSWORD '$DB_PASSWORD';"
fi
if [ "$DRY_RUN" -eq 0 ] && sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null | grep -q 1; then
  log "database $DB_NAME already exists, skipping create"
else
  run sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"
fi

log "ensuring pgvector extension is available in $DB_NAME"
if [ "$DRY_RUN" -eq 0 ] && PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT 1 FROM pg_extension WHERE extname='vector'" 2>/dev/null | grep -q 1; then
  log "vector extension already present, skipping"
else
  if [ "$DRY_RUN" -eq 1 ] || ! PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector" 2>/dev/null; then
    log "CREATE EXTENSION vector failed (package likely missing) - installing postgresql-16-pgvector"
    run $SUDO apt-get update -y
    run $SUDO apt-get install -y postgresql-16-pgvector
    run env PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector"
  fi
fi

# Same four settings + restart as the backend CI job's "Relax Postgres
# durability for the test run" step. Throwaway database: durability costs the
# suite an fsync on every commit for nothing, and max_locks_per_transaction
# needs raising or xdist runs die with "out of shared memory" (see that
# step's comment in deploy.yml for the exact failure).
log "relaxing Postgres durability + raising max_locks_per_transaction"
run env PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
  -c "ALTER SYSTEM SET fsync = off" \
  -c "ALTER SYSTEM SET synchronous_commit = off" \
  -c "ALTER SYSTEM SET full_page_writes = off" \
  -c "ALTER SYSTEM SET max_locks_per_transaction = 1024" \
  -c "SELECT pg_reload_conf()"
run $SUDO service postgresql restart
if [ "$DRY_RUN" -eq 0 ]; then
  for i in $(seq 1 30); do
    pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" && break
    sleep 1
  done
fi

log "writing $ENV_FILE (gitignored - see .gitignore's .env.ci-tests entry)"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "+ write $ENV_FILE"
else
  cat > "$ENV_FILE" <<EOF
# Generated by scripts/cloud-env-setup.sh - safe to regenerate, never commit.
# SORENTO_ENV_FILE=.env.ci-tests points Settings (app/config.py) at this file
# instead of the real .env (see app.config._resolve_settings_env_file).
DATABASE_URL=$DATABASE_URL
DIRECT_URL=$DATABASE_URL
REDIS_URL=$REDIS_URL
JWT_SECRET=$JWT_SECRET
JWT_ALGORITHM=$JWT_ALGORITHM
CORS_ORIGINS=http://localhost:3000
EXTERNAL_API_KEY=$EXTERNAL_API_KEY
EOF
fi

log "backend venv + dependencies"
if [ ! -x "$VENV_PY" ]; then
  PYBIN=python3.12
  command -v "$PYBIN" >/dev/null 2>&1 || PYBIN=python3
  run "$PYBIN" -m venv "$VENV_DIR"
else
  log "venv already exists at $VENV_DIR, skipping creation"
fi
run "$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

# Python 3.12's `venv` writes no .gitignore into the venv (3.13+ does), and the
# repo's .gitignore does not cover sorento_crm_backend/venv - on a VM with no
# global excludes the venv then shows as thousands of untracked files and a
# `git add -A` sweeps it into a commit (seen on the first Linux e2e run).
if [ "$DRY_RUN" -eq 1 ]; then
  echo "+ write $VENV_DIR/.gitignore"
elif [ ! -f "$VENV_DIR/.gitignore" ]; then
  printf '# Created by scripts/cloud-env-setup.sh - keep the venv out of git status.\n*\n' > "$VENV_DIR/.gitignore"
fi

# Before bootstrap_env: its "mcp tool catalog" seeder imports
# `sorento_crm_mcp.catalog`, so with the package installed afterwards the
# seeder logs "No module named 'sorento_crm_mcp'" and the catalogue rows are
# never written (seen on the first Linux e2e run).
log "installing the MCP package (editable) into the backend venv"
run "$VENV_DIR/bin/pip" install -e "$MCP_DIR"

log "bootstrapping the database schema (scripts.bootstrap_env) if not already at alembic head"
NEED_BOOTSTRAP=1
if [ "$DRY_RUN" -eq 0 ] && [ -x "$VENV_DIR/bin/alembic" ]; then
  current="$(cd "$BACKEND_DIR" && SORENTO_ENV_FILE=.env.ci-tests "$VENV_DIR/bin/alembic" current 2>/dev/null | awk '{print $1}')"
  head="$(cd "$BACKEND_DIR" && SORENTO_ENV_FILE=.env.ci-tests "$VENV_DIR/bin/alembic" heads 2>/dev/null | awk '{print $1}')"
  if [ -n "$current" ] && [ "$current" = "$head" ]; then
    NEED_BOOTSTRAP=0
    log "already at alembic head ($current), skipping bootstrap_env"
  fi
fi
if [ "$NEED_BOOTSTRAP" -eq 1 ]; then
  # bootstrap_env's own _require_db_url() reads DATABASE_URL off os.environ
  # directly (not through Settings/SORENTO_ENV_FILE), so it is exported here
  # too - everything else it touches goes through app.database's engine,
  # which does honour SORENTO_ENV_FILE.
  run env SORENTO_ENV_FILE=.env.ci-tests DATABASE_URL="$DATABASE_URL" \
    bash -c "cd '$BACKEND_DIR' && '$VENV_DIR/bin/python' -m scripts.bootstrap_env"
fi

log "frontend dependencies"
NEED_NPM_CI=1
if [ -d "$FRONTEND_DIR/node_modules" ] && [ "$DRY_RUN" -eq 0 ]; then
  if [ "$FRONTEND_DIR/node_modules" -nt "$FRONTEND_DIR/package-lock.json" ]; then
    NEED_NPM_CI=0
    log "node_modules newer than package-lock.json, skipping npm ci"
  fi
fi
if [ "$NEED_NPM_CI" -eq 1 ]; then
  run bash -c "cd '$FRONTEND_DIR' && npm ci --force"
fi

if [ "$DRY_RUN" -eq 1 ]; then
  log "dry run complete, nothing was executed"
  exit 0
fi

log "setup complete"
cat <<SUMMARY

Run the backend suite (same ignore list as CI's tests/ci_excluded.txt, same
gate as .github/workflows/deploy.yml's test-backend job; this VM has no
frontend running, so DEALER_KIT_RENDER_TESTS=skip like that job sets):

  cd sorento_crm_backend
  IGNORES=\$(grep -vE '^\\s*#|^\\s*\$' tests/ci_excluded.txt | sed 's|^|--ignore=|' | tr '\\n' ' ')
  SORENTO_ENV_FILE=.env.ci-tests DEALER_KIT_RENDER_TESTS=skip venv/bin/pytest -q -p no:cacheprovider -n auto --dist loadfile \$IGNORES tests/

That is the single-shard equivalent of CI's test-backend job. Full CI parity
also runs tests/scm/ (test-backend-scm) and two serial steps - serial_ddl
tests and tests/test_migration_*.py - see deploy.yml's test-backend job for
the exact commands if a change touches those.

Run the frontend suite:

  cd sorento_crm_frontend
  npx vitest run

Re-check this environment at any time without changing anything:

  bash scripts/cloud-env-setup.sh --check
SUMMARY
