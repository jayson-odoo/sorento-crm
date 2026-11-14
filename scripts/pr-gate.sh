#!/usr/bin/env bash
# The PR gate, run by crew in the lane sandbox (CI-ZERO-MINUTES, owner 14 Nov 2026).
#
# The same fast checks the hosted `PR gate` job ran on a `ci`-labelled PR, so GitHub Actions
# runs no minute for a PR. Crew runs this on the lane's exact head and posts the result as the
# `PR gate` commit status on that sha; this script never posts anything.
# Contract: documentation/plans/ci/ci-zero-minutes-acceptance-criteria.md section B.
#
#   always    alembic-heads pii ai-coverage outline-guides gitleaks
#   backend   backend-imports backend-collect   (sorento_crm_backend/ or deploy.yml changed)
#   mcp       mcp-imports                       (sorento_crm_mcp/ or deploy.yml changed)
#   frontend  frontend-tsc frontend-eslint      (sorento_crm_frontend/ or deploy.yml changed)
#
# Usage (repo root, origin/main fetched and merged into the lane):
#   scripts/pr-gate.sh                 run every selected check, print the pr-gate line
#   scripts/pr-gate.sh --plan          print the selection (plan.checks=, plan.main=), run nothing
#   scripts/pr-gate.sh --base <ref>    judge against <ref> instead of refs/remotes/origin/main
#
# CREW_CHANGED_FILES (newline-separated repo paths) replaces the git diff; the tests use it.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BACKEND=sorento_crm_backend
FRONTEND=sorento_crm_frontend

PLAN=0
BASE=refs/remotes/origin/main
while [ $# -gt 0 ]; do
  case "$1" in
    --plan) PLAN=1 ;;
    --base) BASE="${2:?--base needs a ref}"; shift ;;
    -h|--help) sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "usage: $0 [--plan] [--base <ref>]" >&2; exit 2 ;;
  esac
  shift
done

HEAD_SHA="$(git rev-parse HEAD)"
if ! BASE_SHA="$(git rev-parse --verify --quiet "$BASE^{commit}")"; then
  echo "$BASE does not resolve to a commit: fetch origin main first" >&2
  echo "pr-gate: $HEAD_SHA FAIL main=$BASE reason=base-not-found"
  exit 1
fi
# The gate judges what lands: a head that does not contain main is not that.
if ! git merge-base --is-ancestor "$BASE_SHA" HEAD; then
  echo "HEAD does not contain $BASE ($BASE_SHA): merge it first" >&2
  echo "pr-gate: $HEAD_SHA FAIL main=$BASE_SHA reason=main-not-merged"
  exit 1
fi

if [ -n "${CREW_CHANGED_FILES+x}" ]; then
  files="$CREW_CHANGED_FILES"
else
  # --no-renames: a rename is its deleted and its added path, both judged.
  # quotePath=false: a non-ASCII name prints as itself and matches its area below.
  files="$(git -c core.quotePath=false diff --name-only --no-renames "$BASE_SHA" HEAD)"
fi
files="$(printf '%s\n' "$files" | sed '/^$/d' | sort -u)"

# Here-strings, not `printf | grep -q` (CI-SCM-FILTER-RACE, see deploy.yml `changes`).
has() { grep -Eq "$1" <<< "$files"; }

# A name git still prints quoted (a control character in it) matches no area: fail closed,
# every area counts as changed.
all=false
has '^"' && all=true
area() { [ "$all" = "true" ] || has "$1"; }
checks=(alembic-heads pii ai-coverage outline-guides gitleaks)
area '^(sorento_crm_backend/|\.github/workflows/deploy\.yml$)' && checks+=(backend-imports backend-collect)
area '^(sorento_crm_mcp/|\.github/workflows/deploy\.yml$)' && checks+=(mcp-imports)
area '^(sorento_crm_frontend/|\.github/workflows/deploy\.yml$)' && checks+=(frontend-tsc frontend-eslint)

if [ "$PLAN" = "1" ]; then
  printf 'plan.checks=%s\nplan.main=%s\n' "${checks[*]}" "$BASE_SHA"
  exit 0
fi

# --- run ------------------------------------------------------------------------------------
# The result must describe the head sha: uncommitted changes to tracked files refuse the run.
# Untracked files (venv, env files) are normal in a sandbox and allowed.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "the working tree has uncommitted changes to tracked files: commit or stash them first" >&2
  echo "pr-gate: $HEAD_SHA FAIL main=$BASE_SHA reason=dirty-tree"
  exit 1
fi
PY=python3
[ -x "$ROOT/$BACKEND/venv/bin/python" ] && PY="$ROOT/$BACKEND/venv/bin/python"

# Backend checks read .env.ci-tests when scripts/cloud-env-setup.sh wrote it. Settings ranks
# the process environment above the env file, so an exported database or Redis URL is dropped.
backend_env=()
if [ -f "$BACKEND/.env.ci-tests" ]; then
  backend_env=(env -u DATABASE_URL -u DIRECT_URL -u REDIS_URL SORENTO_ENV_FILE=.env.ci-tests)
fi

need_node_modules() {
  [ -d "$FRONTEND/node_modules" ] && return 0
  echo "$FRONTEND/node_modules is missing: run npm install --force in $FRONTEND first" >&2
  return 1
}

run_check() {
  case "$1" in
    alembic-heads) "$PY" scripts/ci_alembic_heads.py ;;
    pii) "$PY" scripts/pii_guard.py ;;
    ai-coverage) "$PY" scripts/ci_ai_coverage.py --base "$BASE_SHA" ;;
    outline-guides) "$PY" scripts/sync_user_guides_outline.py check ;;
    gitleaks)
      RANGE="$BASE_SHA..$HEAD_SHA" GITLEAKS_CACHE_DIR="${GITLEAKS_CACHE_DIR:-$HOME/.cache/gitleaks}" \
        bash scripts/ci_gitleaks.sh ;;
    backend-imports)
      # The worker's import order differs from app.main's: a circular import can pass one only.
      (cd "$BACKEND" \
        && ${backend_env[@]+"${backend_env[@]}"} "$PY" -c "from app.main import app; print('import ok')" \
        && ${backend_env[@]+"${backend_env[@]}"} "$PY" -c "import worker; from app.scheduler.task_scheduler import start_scheduler; print('worker import chain ok')") ;;
    backend-collect)
      (cd "$BACKEND" && ${backend_env[@]+"${backend_env[@]}"} "$PY" -m pytest --collect-only -q -p no:cacheprovider) ;;
    mcp-imports)
      CRM_BASE_URL=http://localhost:8000 EXTERNAL_API_KEY=ci-dummy "$PY" -c \
        "from importlib.metadata import version; from sorento_crm_mcp.server import create_mcp_app; print('mcp', version('mcp'), 'entrypoint imports ok')" ;;
    frontend-tsc)
      need_node_modules \
        && (cd "$FRONTEND" && export NODE_OPTIONS=--max-old-space-size=4096 && npx next typegen && npm run typecheck) ;;
    frontend-eslint)
      # Added, copied, modified or renamed files only: a deleted file has nothing to lint.
      need_node_modules \
        && (cd "$FRONTEND" && git diff -z --name-only --relative --diff-filter=ACMR "$BASE_SHA" HEAD -- \
              '*.ts' '*.tsx' '*.js' '*.jsx' '*.mjs' '*.cjs' \
            | xargs -0 -r npx eslint --no-warn-ignored --) ;;
  esac
}

failed=()
for id in "${checks[@]}"; do
  echo "== $id"
  if run_check "$id"; then
    echo "== $id: pass"
  else
    echo "== $id: FAIL"
    failed+=("$id")
  fi
done

join() { local IFS=,; echo "$*"; }
echo
if [ "${#failed[@]}" -eq 0 ]; then
  echo "pr-gate: $HEAD_SHA PASS main=$BASE_SHA checks=$(join "${checks[@]}")"
  exit 0
fi
echo "pr-gate: $HEAD_SHA FAIL main=$BASE_SHA checks=$(join "${checks[@]}") failed=$(join "${failed[@]}")"
exit 1
