#!/usr/bin/env bash
# Release delta on top of the last green nightly sweep (owner ruling 4 Nov 2026;
# documentation/agents/cloud-lanes.md "Nightly sweep"). Given the nightly's sha and the release
# head, runs in a Claude Code cloud sandbox:
#   - alembic heads == 1 and scripts.bootstrap_env + `alembic upgrade head` on a FRESH database
#   - tests/test_migration_*.py serially
#   - tests/scm/ under xdist, then its serial_ddl tests serially
#   - every backend test file the diff touches, plus every test file that imports a touched
#     app module (by dotted path or `from <pkg> import <module>`), minus tests/scm, the
#     migration tests and tests/ci_excluded.txt; under xdist, then their serial_ddl tests
#   - frontend: the FULL npx vitest run
# and prints ONE line on stdout:
#   crew-tests: <head sha> delta since nightly <nightly sha> backend N passed/F failed, vitest N/F
# The selected files are in <output dir>/selected.txt.
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
# shellcheck disable=SC2207
IGNORES=($(sweep_ignores))
HEADS="$(venv/bin/alembic heads 2>/dev/null | grep -c '(head)' || true)"
UPGRADE=ok
venv/bin/alembic upgrade head > "$OUT/alembic_upgrade.log" 2>&1 || UPGRADE=FAILED

python3 - "$BASE" "$HEAD_SHA" > "$OUT/selected.txt" <<'PY'
import glob, os, re, subprocess, sys
base, head = sys.argv[1:3]
changed = subprocess.check_output(["git", "diff", "--name-only", base, head, "--", "."], text=True).split()
changed = [p.split("sorento_crm_backend/", 1)[1] for p in changed if p.startswith("sorento_crm_backend/")]
excluded = {l.strip() for l in open("tests/ci_excluded.txt") if l.strip() and not l.startswith("#")}
modules = [p[:-3].replace("/", ".") for p in changed if p.startswith("app/") and p.endswith(".py")]
patterns = []
for mod in modules:
    pkg, _, name = mod.rpartition(".")
    patterns.append(re.compile(
        rf"\b{re.escape(mod)}\b|from\s+{re.escape(pkg)}\s+import\s+(\([^)]*|[^\n]*)\b{re.escape(name)}\b"))
selected = {p for p in changed if p.startswith("tests/") and os.path.basename(p).startswith("test_")
            and p.endswith(".py") and os.path.exists(p)}
for path in glob.glob("tests/**/test_*.py", recursive=True):
    if any(p.search(open(path).read()) for p in patterns):
        selected.add(path)
keep = sorted(p for p in selected if not p.startswith("tests/scm/")
              and not os.path.basename(p).startswith("test_migration_") and p not in excluded)
print("\n".join(keep))
PY
sweep_log "selected $(grep -c . "$OUT/selected.txt" || true) backend test files ($OUT/selected.txt)"

# shellcheck disable=SC2046
sweep_pytest migrations "$OUT" -p no:xdist $(ls tests/test_migration_*.py)
sweep_pytest scm "$OUT" "${SWEEP_XDIST[@]}" -m "not serial_ddl" "${IGNORES[@]}" tests/scm/
sweep_pytest scm_serial_ddl "$OUT" -p no:xdist -m serial_ddl "${IGNORES[@]}" tests/scm/
if [ -s "$OUT/selected.txt" ]; then
  # shellcheck disable=SC2046
  sweep_pytest selected "$OUT" "${SWEEP_XDIST[@]}" -m "not serial_ddl" $(cat "$OUT/selected.txt")
  # shellcheck disable=SC2046
  sweep_pytest selected_serial_ddl "$OUT" -p no:xdist -m serial_ddl $(cat "$OUT/selected.txt")
fi

read -r BE_PASS BE_FAIL < <(sweep_count_backend "$OUT")
read -r FE_PASS FE_FAIL < <(sweep_vitest "$TREE/sorento_crm_frontend" "$OUT")

sweep_log "alembic heads: $HEADS; upgrade head on the fresh db: $UPGRADE; output: $OUT"
echo "crew-tests: $HEAD_SHA delta since nightly $BASE backend $BE_PASS passed/$BE_FAIL failed, vitest $FE_PASS/$FE_FAIL"
[ "$BE_FAIL" -eq 0 ] && [ "$FE_FAIL" -eq 0 ] && [ "$HEADS" -eq 1 ] && [ "$UPGRADE" = ok ]
