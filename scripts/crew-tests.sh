#!/usr/bin/env bash
# The tests a lane runs in its cloud sandbox before crew-done (CI-CLOUD-GATE, 4 Nov 2026).
#
# The PR gate on GitHub runs fast checks only (no pytest execution, no vitest). This script runs
# what that gate used to run, on the lane's exact head, and prints the `crew-tests:` line the
# lane posts on its PR (contract: documentation/agents/cloud-lanes.md "Tests before crew-done"):
#
#   backend  every changed backend test file plus every test file that imports a changed module
#            (sorento_crm_backend/scripts/ci_select_tests.py, the selection the PR gate used),
#            the forms lifecycle chains when forms code changed (FORMS-REGRESSION, 30 Oct), and
#            the regression guards (tests/test_lessons_learnt_regressions.py); ci_excluded.txt
#            entries and paths the checkout no longer holds are dropped. Postgres, never sqlite,
#            through SORENTO_ENV_FILE=.env.ci-tests (scripts/cloud-env-setup.sh writes it).
#   mcp      sorento_crm_mcp/tests when the MCP tree changed.
#   vitest   `vitest run --changed <base>` plus the source-scanning guards
#            (sorento_crm_frontend/scripts/source-guard-tests.sh) when the frontend changed.
#
# Usage (repo root, after `bash scripts/cloud-env-setup.sh`):
#   scripts/crew-tests.sh                 run, print the crew-tests line, exit non-zero on a failure
#   scripts/crew-tests.sh --plan          print the selection (plan.<area>=...), run nothing
#   scripts/crew-tests.sh --base <ref>    diff against <ref> instead of merge-base(origin/main, HEAD)
#
# CREW_CHANGED_FILES (newline-separated repo paths) replaces the git diff; the tests use it.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BACKEND=sorento_crm_backend
FRONTEND=sorento_crm_frontend

PLAN=0
BASE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --plan) PLAN=1 ;;
    --base) BASE="$2"; shift ;;
    -h|--help) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "usage: $0 [--plan] [--base <ref>]" >&2; exit 2 ;;
  esac
  shift
done

if [ -n "${CREW_CHANGED_FILES+x}" ]; then
  files="$CREW_CHANGED_FILES"
  BASE="${BASE:-HEAD}"
else
  if [ -z "$BASE" ]; then
    git fetch --no-tags --quiet origin +refs/heads/main:refs/remotes/origin/main || true
    BASE="$(git merge-base refs/remotes/origin/main HEAD)"
  fi
  # --no-renames: a rename is its deleted and its added path, both judged.
  files="$(git diff --name-only --no-renames "$BASE" HEAD)"
fi
files="$(printf '%s\n' "$files" | sed '/^$/d' | sort -u)"

# Here-strings, not `printf | grep -q` (CI-SCM-FILTER-RACE, see deploy.yml `changes`).
has() { grep -Eq "$1" <<< "$files"; }

# Same classes as deploy.yml `changes`: shell-safe characters only reach a command line.
BACKEND_TESTS_RE='^sorento_crm_backend/tests/([A-Za-z0-9_.-]+/)*test_[A-Za-z0-9_.-]*\.py$'
BACKEND_CODE_RE='^sorento_crm_backend/(app|scripts|tests)/([A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.py$'
# The forms lifecycle paths the PR gate's FORMS-REGRESSION step used (owner, 30 Oct 2026).
FORMS_RE='^sorento_crm_backend/(app/(api/v1/(procurement|complaints|sla|public|projects|dealer_kit)/|services/(procurement_service|complaints?_[a-z_]+|portal_[a-z_]+|form_[a-z_]+|handling_lock_service|sla_[a-z_]+|submission_status|revision_fence|response_gate|price_tag_[a-z_]+|sample_request_service|project_registration_service|respond_messaging_service|respond_identifier|integration_service|notification_service|queue_service|user_service|coverage_subscription_service|crm_chat_outbound_webhook)\.py$|services/dealer_kit/|schemas/(procurement|complaints|sla|portal|price_tag|sample_request|projects)[a-z_]*\.py$|models/(procurement|complaints|sla|portal|price_tag|sample_request|projects|access|integration|user)\.py$|tasks/respond_io_tasks\.py$)|tests/(test_forms_chain_[a-z_]+|_forms_chain_support|_project_registration_support|_sample_request_seed|_portal_grant|_pg_fixture|conftest|test_form_handling_lock_routes|test_sla_due_escalations|test_complaint_status_guard)\.py$)'

backend_list=""
forms=false
if has '^sorento_crm_backend/'; then
  selected=""
  inputs="$(grep -E "$BACKEND_CODE_RE" <<< "$files" || true)"
  if [ -n "$inputs" ]; then
    out="$(mktemp)"
    printf '%s\n' "$inputs" \
      | GITHUB_OUTPUT="$out" python3 "$BACKEND/scripts/ci_select_tests.py" --root "$BACKEND" --scm false >&2
    selected="$(sed -n 's/^tests=//p' "$out")"
    rm -f "$out"
  fi
  chains=""
  if has "$FORMS_RE"; then
    forms=true
    chains="$(cd "$BACKEND" && ls tests/test_forms_chain_*.py tests/test_form_handling_lock_routes.py \
                tests/test_sla_due_escalations.py tests/test_complaint_status_guard.py 2>/dev/null || true)"
  fi
  excluded="$(grep -vE '^\s*#|^\s*$' "$BACKEND/tests/ci_excluded.txt" 2>/dev/null || true)"
  for path in $selected; do
    rel="${path#"$BACKEND"/}"
    if [ ! -f "$BACKEND/$rel" ]; then
      echo "not run: $rel (not in the checkout)" >&2
    elif grep -qxF "$rel" <<< "$excluded"; then
      echo "not run: $rel (tests/ci_excluded.txt)" >&2
    else
      backend_list="$backend_list $rel"
    fi
  done
  backend_list="$(printf '%s\n' $backend_list $chains tests/test_lessons_learnt_regressions.py | sed '/^$/d' | sort -u | tr '\n' ' ' | sed 's/ $//')"
fi
mcp=false; has '^sorento_crm_mcp/' && mcp=true
vitest=false; has '^sorento_crm_frontend/' && vitest=true

if [ "$PLAN" = "1" ]; then
  printf 'plan.backend=%s\nplan.forms=%s\nplan.mcp=%s\nplan.vitest=%s\n' "$backend_list" "$forms" "$mcp" "$vitest"
  exit 0
fi

# --- run ------------------------------------------------------------------------------------
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "the working tree has uncommitted changes: commit them, so the result is for the exact head" >&2
  exit 2
fi
HEAD_SHA="$(git rev-parse HEAD)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PY="$ROOT/$BACKEND/venv/bin/python"
commands=()
rc=0

# junit XML -> "passed failed" summed over the files given.
count() {
  python3 - "$@" <<'PY'
import sys, xml.etree.ElementTree as ET
p = f = 0
for path in sys.argv[1:]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        continue
    suites = [root] if root.tag == "testsuite" else root.iter("testsuite")
    for s in suites:
        t = int(s.get("tests", 0)); bad = int(s.get("failures", 0)) + int(s.get("errors", 0))
        p += t - bad - int(s.get("skipped", 0)); f += bad
print(p, f)
PY
}

n=0
pytest_pass() {  # args: pytest arguments; junit into $TMP/<area>-<n>.xml
  local area="$1"; shift
  n=$((n + 1))
  commands+=("(cd $BACKEND && SORENTO_ENV_FILE=.env.ci-tests venv/bin/python -m pytest $*)")
  (cd "$BACKEND" && SORENTO_ENV_FILE=.env.ci-tests "$PY" -m pytest -q -p no:cacheprovider \
      --junitxml="$TMP/$area-$n.xml" "$@") || { r=$?; [ "$r" -eq 5 ] || rc=1; }
}

backend_summary="not run (no backend change)"
if [ -n "$backend_list" ]; then
  # The PR gate's split: tests/scm and the main tree in separate sessions (several main-tree
  # files import tests.scm.conftest by name), xdist for all but serial_ddl, then serial_ddl,
  # then the migration tests serially. Exit 5 (nothing collected) is not a failure.
  main=""; scm=""; migrations=""
  for f in $backend_list; do
    case "$f" in
      tests/test_migration_*.py) migrations="$migrations $f" ;;
      tests/scm/*) scm="$scm $f" ;;
      *) main="$main $f" ;;
    esac
  done
  for pool in "$main" "$scm"; do
    [ -n "$pool" ] || continue
    # shellcheck disable=SC2086
    pytest_pass backend -n auto --dist loadfile --max-worker-restart 0 -p tests._xdist_crash_guard -m "not serial_ddl" $pool
    # shellcheck disable=SC2086
    pytest_pass backend -p no:xdist -m serial_ddl $pool
  done
  # shellcheck disable=SC2086
  [ -z "$migrations" ] || pytest_pass backend -p no:xdist $migrations
  read -r bp bf <<< "$(count "$TMP"/backend-*.xml)"
  backend_summary="$bp passed/$bf failed"
fi

mcp_summary=""
if [ "$mcp" = "true" ]; then
  commands+=("$BACKEND/venv/bin/python -m pytest sorento_crm_mcp/tests")
  CRM_BASE_URL=http://localhost:8000 EXTERNAL_API_KEY=ci-dummy \
    "$PY" -m pytest -q -p no:cacheprovider --junitxml="$TMP/mcp.xml" sorento_crm_mcp/tests || rc=1
  read -r mp mf <<< "$(count "$TMP/mcp.xml")"
  mcp_summary=", mcp $mp/$mf"
fi

vitest_summary="not run (no frontend change)"
if [ "$vitest" = "true" ]; then
  commands+=("(cd $FRONTEND && npx vitest run --changed $BASE --passWithNoTests)")
  (cd "$FRONTEND" && npx vitest run --changed "$BASE" --passWithNoTests \
      --reporter=default --reporter=junit --outputFile.junit="$TMP/vitest-1.xml") || rc=1
  commands+=("(cd $FRONTEND && scripts/source-guard-tests.sh | xargs -0 -r npx vitest run)")
  (cd "$FRONTEND" && set -o pipefail && scripts/source-guard-tests.sh \
      | xargs -0 -r npx vitest run --reporter=default --reporter=junit --outputFile.junit="$TMP/vitest-2.xml") || rc=1
  read -r vp vf <<< "$(count "$TMP"/vitest-*.xml)"
  vitest_summary="$vp/$vf"
fi

echo
echo "crew-tests: $HEAD_SHA backend $backend_summary, vitest $vitest_summary$mcp_summary"
echo "base: $BASE"
echo "commands:"
for c in "${commands[@]}"; do echo "  $c"; done
exit "$rc"
