#!/usr/bin/env bash
# Full-suite sweep of one main sha in a Claude Code cloud sandbox (CI-CLOUD-GATE nightly,
# owner ruling 4 Nov 2026; documentation/agents/cloud-lanes.md "Nightly sweep").
#
# Sets up the sandbox (scripts/cloud-env-setup.sh plus the gaps in scripts/sweep-lib.sh),
# bootstraps a FRESH database from the sha's own code, then runs deploy.yml's split:
#   1. tests/ minus tests/scm, tests/test_migration_*.py, serial_ddl and tests/ci_excluded.txt,
#      under xdist in 10 pytest-split groups (one pytest session per group)
#   2. tests/test_migration_*.py serially
#   3. -m serial_ddl over the same tree, serially
#   4. tests/scm/ under xdist (-m "not serial_ddl"), then its serial_ddl tests serially
#   5. frontend: npx vitest run
# and prints ONE line on stdout:
#   crew-tests: <40-char sha> backend N passed/F failed, vitest N/F
# Logs, junit files and failed.txt (failing test ids) stay in the printed output directory.
#
# Usage: bash scripts/nightly-sweep.sh [<sha or ref>]   (default origin/main)
# Takes about 2.5 h on a 4-core sandbox. Exit 0 when everything passed, 1 otherwise.
set -euo pipefail

source "$(dirname "$0")/sweep-lib.sh"

REF="${1:-origin/main}"
git -C "$SWEEP_REPO_ROOT" fetch -q origin main || true
SHA="$(git -C "$SWEEP_REPO_ROOT" rev-parse --verify "$REF^{commit}")"
OUT="${SWEEP_OUT:-$(mktemp -d)/nightly-${SHA:0:10}}"
mkdir -p "$OUT"
DB=sorento_sweep
TREE="$(mktemp -d)/tree"
trap 'sweep_worktree_remove "$TREE"' EXIT

sweep_env_setup
sweep_pgvector
sweep_dns
sweep_worktree "$SHA" "$TREE" "$DB"
sweep_fresh_db "$DB" "$TREE/sorento_crm_backend"

cd "$TREE/sorento_crm_backend"
export SORENTO_ENV_FILE=.env.ci-tests DEALER_KIT_RENDER_TESTS=skip
export DATABASE_URL="postgresql://$SWEEP_DB_USER:$SWEEP_DB_PASSWORD@localhost:5432/$DB"
# shellcheck disable=SC2207
IGNORES=($(sweep_ignores))
HEADS="$(venv/bin/alembic heads 2>/dev/null | grep -c '(head)' || true)"

for group in $(seq 1 10); do
  sweep_pytest "main_$group" "$OUT" "${SWEEP_XDIST[@]}" --splits 10 --group "$group" \
    --ignore-glob='tests/test_migration_*.py' -m "not serial_ddl" "${IGNORES[@]}" \
    --ignore=tests/scm tests/
done
# shellcheck disable=SC2046
sweep_pytest migrations "$OUT" -p no:xdist $(ls tests/test_migration_*.py)
sweep_pytest serial_ddl "$OUT" -p no:xdist -m serial_ddl --ignore-glob='tests/test_migration_*.py' \
  "${IGNORES[@]}" --ignore=tests/scm tests/
sweep_pytest scm "$OUT" "${SWEEP_XDIST[@]}" -m "not serial_ddl" "${IGNORES[@]}" tests/scm/
sweep_pytest scm_serial_ddl "$OUT" -p no:xdist -m serial_ddl "${IGNORES[@]}" tests/scm/

read -r BE_PASS BE_FAIL < <(sweep_count_backend "$OUT")
read -r FE_PASS FE_FAIL < <(sweep_vitest "$TREE/sorento_crm_frontend" "$OUT")

sweep_log "alembic heads: $HEADS; output: $OUT (failing ids: $OUT/failed.txt, vitest: $OUT/vitest.log)"
echo "crew-tests: $SHA backend $BE_PASS passed/$BE_FAIL failed, vitest $FE_PASS/$FE_FAIL"
[ "$BE_FAIL" -eq 0 ] && [ "$FE_FAIL" -eq 0 ] && [ "$HEADS" -eq 1 ]
