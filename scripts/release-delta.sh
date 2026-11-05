#!/usr/bin/env bash
# Release delta on top of the last green nightly sweep (owner ruling 4 Nov 2026;
# documentation/agents/cloud-lanes.md "Nightly sweep + release delta"). Given the nightly's sha and the release
# head, runs in a Claude Code cloud sandbox:
#   - alembic heads == 1 and scripts.bootstrap_env + `alembic upgrade head` on a FRESH database
#   - ONLY the affected tests (owner ruling 5 Nov 2026, RELEASE-DELTA-AFFECTED): the backend test
#     files sorento_crm_backend/scripts/release_delta_select.py picks from the import graph
#     (dependents of the change, the tests of what it calls, tests/scm/ only when reached, the
#     migration tests only on alembic/ or app/models/ changes; the full suite on a conftest /
#     test infra / dependency / env bootstrap change or a graph failure), run as the PR gate
#     split them: main tree and tests/scm/ each under xdist then serial_ddl, migrations serially
#   - frontend: `vitest related --run <changed files>` plus the source-scanning guards; the FULL
#     vitest only when shared config or test setup changed; nothing without a frontend change
# and prints ONE line on stdout:
#   crew-tests: <head sha> delta since nightly <nightly sha> backend N passed/F failed
#     (selected S of M test files: <why>), vitest N/F (<mode>)
# The selected files are in <output dir>/selected.txt, each with its reason in selected_why.txt.
#
# Usage: bash scripts/release-delta.sh <nightly sha> [<release head>]   (head default origin/main)
# Exit 0 when everything passed, 1 otherwise.
set -euo pipefail

source "$(dirname "$0")/sweep-lib.sh"

if [ $# -lt 1 ]; then
  echo "usage: $0 <nightly sha> [<release head>]" >&2
  exit 2
fi
git -C "$SWEEP_REPO_ROOT" fetch -q origin main || true
BASE="$(git -C "$SWEEP_REPO_ROOT" rev-parse --verify "$1^{commit}")"
HEAD_SHA="$(git -C "$SWEEP_REPO_ROOT" rev-parse --verify "${2:-origin/main}^{commit}")"
git -C "$SWEEP_REPO_ROOT" merge-base --is-ancestor "$BASE" "$HEAD_SHA" \
  || { echo "$BASE is not an ancestor of $HEAD_SHA" >&2; exit 2; }
OUT="${SWEEP_OUT:-$(mktemp -d)/delta-${HEAD_SHA:0:10}}"
mkdir -p "$OUT"
DB=sorento_delta
TREE="$(mktemp -d)/tree"
trap 'sweep_worktree_remove "$TREE"' EXIT

sweep_env_setup
sweep_pgvector
sweep_dns
sweep_worktree "$HEAD_SHA" "$TREE" "$DB"
sweep_fresh_db "$DB" "$TREE/sorento_crm_backend"

cd "$TREE/sorento_crm_backend"
export SORENTO_ENV_FILE=.env.ci-tests DEALER_KIT_RENDER_TESTS=skip
export DATABASE_URL="postgresql://$SWEEP_DB_USER:$SWEEP_DB_PASSWORD@localhost:5432/$DB"
HEADS="$(venv/bin/alembic heads 2>/dev/null | grep -c '(head)' || true)"
UPGRADE=ok
venv/bin/alembic upgrade head > "$OUT/alembic_upgrade.log" 2>&1 || UPGRADE=FAILED

# The head's own selector; a head older than the selector (a re-run on a past range) borrows
# this checkout's copy, pointed at the head's tree.
SELECTOR=scripts/release_delta_select.py
[ -f "$SELECTOR" ] || SELECTOR="$SWEEP_REPO_ROOT/sorento_crm_backend/scripts/release_delta_select.py"
SEL="$(venv/bin/python "$SELECTOR" --backend "$PWD" --base "$BASE" --head "$HEAD_SHA" --out "$OUT" \
  2> "$OUT/selector.log")" || SEL="backend=failed"
sel() { sed -n "s/^$1=//p" <<< "$SEL"; }
if [ "$(sel backend)" = failed ]; then
  sweep_log "the selector failed ($OUT/selector.log): running every test file"
  find tests -name 'test_*.py' | sed 's#^\./##' | sort | grep -vxF -f <(grep -vE '^\s*#|^\s*$' tests/ci_excluded.txt) \
    > "$OUT/selected.txt" || true
  SEL="backend=full
backend_reason=selector failed
backend_selected=$(grep -c . "$OUT/selected.txt" || true)
backend_total=$(grep -c . "$OUT/selected.txt" || true)
backend_scm=$(grep -c '^tests/scm/' "$OUT/selected.txt" || true)
vitest=full
vitest_reason=selector failed"
fi
sweep_log "backend: $(sel backend), selected $(sel backend_selected) of $(sel backend_total) test files ($(sel backend_scm) under tests/scm): $(sel backend_reason)"
sweep_log "vitest: $(sel vitest): $(sel vitest_reason)"

MAIN=(); SCM=(); MIGRATIONS=()
while IFS= read -r f; do
  case "$f" in
    tests/test_migration_*.py) MIGRATIONS+=("$f") ;;
    tests/scm/*) SCM+=("$f") ;;
    *) MAIN+=("$f") ;;
  esac
done < "$OUT/selected.txt"
# Exit 5 (nothing collected, e.g. no serial_ddl test in the pool) counts nothing either way.
if [ ${#MIGRATIONS[@]} -gt 0 ]; then
  sweep_pytest migrations "$OUT" -p no:xdist "${MIGRATIONS[@]}"
fi
if [ ${#SCM[@]} -gt 0 ]; then
  sweep_pytest scm "$OUT" "${SWEEP_XDIST[@]}" -m "not serial_ddl" "${SCM[@]}"
  sweep_pytest scm_serial_ddl "$OUT" -p no:xdist -m serial_ddl "${SCM[@]}"
fi
if [ ${#MAIN[@]} -gt 0 ]; then
  sweep_pytest selected "$OUT" "${SWEEP_XDIST[@]}" -m "not serial_ddl" "${MAIN[@]}"
  sweep_pytest selected_serial_ddl "$OUT" -p no:xdist -m serial_ddl "${MAIN[@]}"
fi

read -r BE_PASS BE_FAIL < <(sweep_count_backend "$OUT")
FE="$TREE/sorento_crm_frontend"
case "$(sel vitest)" in
  full)
    read -r FE_PASS FE_FAIL < <(sweep_vitest "$FE" "$OUT") ;;
  related)
    mapfile -t RELATED < "$OUT/vitest_related.txt"
    mapfile -d '' GUARDS < <(cd "$FE" && scripts/source-guard-tests.sh)
    # `vitest related` with no file would mean something else: only deletions run the guards only.
    P1=0; F1=0; P2=0; F2=0
    [ ${#RELATED[@]} -eq 0 ] \
      || read -r P1 F1 < <(sweep_vitest "$FE" "$OUT" vitest_related related --run --passWithNoTests "${RELATED[@]}")
    [ ${#GUARDS[@]} -eq 0 ] || read -r P2 F2 < <(sweep_vitest "$FE" "$OUT" vitest_guards run "${GUARDS[@]}")
    FE_PASS=$((P1 + P2)); FE_FAIL=$((F1 + F2)) ;;
  *)
    FE_PASS=0; FE_FAIL=0 ;;
esac

sweep_log "alembic heads: $HEADS; upgrade head on the fresh db: $UPGRADE; output: $OUT"
echo "crew-tests: $HEAD_SHA delta since nightly $BASE backend $BE_PASS passed/$BE_FAIL failed (selected $(sel backend_selected) of $(sel backend_total) test files: $(sel backend_reason)), vitest $FE_PASS/$FE_FAIL ($(sel vitest))"
[ "$BE_FAIL" -eq 0 ] && [ "$FE_FAIL" -eq 0 ] && [ "$HEADS" -eq 1 ] && [ "$UPGRADE" = ok ]
