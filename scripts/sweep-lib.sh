# Shared by scripts/nightly-sweep.sh and scripts/release-delta.sh. Source it, do not run it.
#
# What a Claude Code cloud sandbox needs beyond scripts/cloud-env-setup.sh to run the suite the
# way deploy.yml's test-backend / test-backend-scm jobs do (each item measured on the 4 Nov 2026
# release sweep, RELEASE-SWEEP-4NOV-PM, #2171):
#   - pgvector >= 0.8: Ubuntu's postgresql-16-pgvector is 0.6.0, which has no hnsw.iterative_scan
#     (app/services/embedding_indexes.py), so 3 tests fail that pass on CI's pgvector/pgvector:pg16.
#   - automate-sorento.foundryx.my must resolve: the sandbox DNS does not, and
#     app/services/outbound_url_guard.py answers 422, so 12 tests/chatbot tests fail.
#   - DATABASE_URL exported: tests/scm/conftest.py's _pg_url reads os.environ / .env only, not
#     SORENTO_ENV_FILE; without it 25 tests/scm tests error and ~2,100 skip. CI sets it.
#   - a fresh database bootstrapped from the code under test (scripts.bootstrap_env), as CI does.

SWEEP_REPO_ROOT="$(git rev-parse --show-toplevel)"
SWEEP_DB_USER=sorento
SWEEP_DB_PASSWORD=sorento
SWEEP_PGVECTOR_TAG=v0.8.0
# Any public address will do: the tests only need the name to resolve to a non-private IP, they
# never connect to it (the outbound calls are mocked).
SWEEP_DNS_HOST=automate-sorento.foundryx.my
SWEEP_DNS_IP=104.21.0.1

sweep_log() { echo "[sweep] $*" >&2; }

sweep_sudo() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi; }

# Postgres, Redis, venv, node_modules, MCP package (idempotent).
sweep_env_setup() {
  bash "$SWEEP_REPO_ROOT/scripts/cloud-env-setup.sh" >&2
}

# Build and install pgvector $SWEEP_PGVECTOR_TAG when the packaged one is older.
sweep_pgvector() {
  local have
  have="$(sweep_sudo -u postgres psql -tAc "SELECT default_version FROM pg_available_extensions WHERE name='vector'" | tr -d ' ')"
  if [ -n "$have" ] && printf '%s\n0.8.0\n' "$have" | sort -V -C 2>/dev/null && [ "$have" != "0.8.0" ]; then
    sweep_log "pgvector $have < 0.8.0: building $SWEEP_PGVECTOR_TAG"
    local src
    src="$(mktemp -d)"
    sweep_sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -q postgresql-server-dev-16 >&2
    git clone -q --depth 1 -b "$SWEEP_PGVECTOR_TAG" https://github.com/pgvector/pgvector "$src/pgvector"
    (cd "$src/pgvector" && make -s OPTFLAGS="" >&2 && sweep_sudo make -s install >&2)
    rm -rf "$src"
  else
    sweep_log "pgvector available: $have"
  fi
}

sweep_dns() {
  if getent hosts "$SWEEP_DNS_HOST" >/dev/null; then
    sweep_log "$SWEEP_DNS_HOST resolves"
  else
    sweep_log "adding $SWEEP_DNS_HOST -> $SWEEP_DNS_IP to /etc/hosts (sandbox has no DNS for it)"
    echo "$SWEEP_DNS_IP $SWEEP_DNS_HOST" | sweep_sudo tee -a /etc/hosts >/dev/null
  fi
}

# sweep_worktree <sha> <dir>: a detached worktree of <sha> sharing the primary checkout's venv,
# node_modules and .env.ci-tests (pointed at database <db>).
sweep_worktree() {
  local sha="$1" dir="$2" db="$3"
  git -C "$SWEEP_REPO_ROOT" worktree add -q --detach "$dir" "$sha"
  ln -sfn "$SWEEP_REPO_ROOT/sorento_crm_backend/venv" "$dir/sorento_crm_backend/venv"
  ln -sfn "$SWEEP_REPO_ROOT/sorento_crm_frontend/node_modules" "$dir/sorento_crm_frontend/node_modules"
  sed "s#/sorento_ci\$#/$db#" "$SWEEP_REPO_ROOT/sorento_crm_backend/.env.ci-tests" \
    > "$dir/sorento_crm_backend/.env.ci-tests"
}

sweep_worktree_remove() {
  git -C "$SWEEP_REPO_ROOT" worktree remove --force "$1" 2>/dev/null || true
}

# sweep_fresh_db <db> <backend dir>: drop, create, vector, bootstrap from that tree's code.
sweep_fresh_db() {
  local db="$1" backend="$2"
  sweep_sudo -u postgres dropdb --if-exists "$db"
  sweep_sudo -u postgres createdb -O "$SWEEP_DB_USER" "$db"
  sweep_sudo -u postgres psql -d "$db" -qc "CREATE EXTENSION IF NOT EXISTS vector"
  (cd "$backend" && SORENTO_ENV_FILE=.env.ci-tests \
    DATABASE_URL="postgresql://$SWEEP_DB_USER:$SWEEP_DB_PASSWORD@localhost:5432/$db" \
    venv/bin/python -m scripts.bootstrap_env >&2)
}

# sweep_pytest <name> <out dir> <pytest args...>: one pytest session, junit to <out>/<name>.xml.
# Runs from the current directory (a backend dir). Never fails the caller.
sweep_pytest() {
  local name="$1" out="$2"
  shift 2
  sweep_log "pytest $name"
  venv/bin/python -m pytest -q -p no:cacheprovider -rfE --junitxml="$out/$name.xml" "$@" \
    > "$out/$name.log" 2>&1 || true
  sweep_log "  $(tail -1 "$out/$name.log")"
}

# The deploy.yml xdist flags for the executing gate.
SWEEP_XDIST=(-n auto --dist loadfile --max-worker-restart 0 -p tests._xdist_crash_guard)

sweep_ignores() {
  grep -vE '^\s*#|^\s*$' tests/ci_excluded.txt | sed 's|^|--ignore=|' | tr '\n' ' '
}

# Prints "<passed> <failed>" over every junit file in <out> (errors count as failed) and writes
# the failing test ids to <out>/failed.txt.
sweep_count_backend() {
  python3 - "$1" <<'PY'
import glob, sys, xml.etree.ElementTree as ET
out = sys.argv[1]
passed = failed = 0
bad = []
for path in sorted(glob.glob(f"{out}/*.xml")):
    for case in ET.parse(path).getroot().iter("testcase"):
        kids = {c.tag for c in case}
        if kids & {"failure", "error"}:
            failed += 1
            bad.append(f"{case.get('classname')}::{case.get('name')}")
        elif "skipped" not in kids:
            passed += 1
open(f"{out}/failed.txt", "w").write("\n".join(bad) + ("\n" if bad else ""))
print(passed, failed)
PY
}

# sweep_vitest <frontend dir> <out>: prints "<passed> <failed>".
sweep_vitest() {
  local fe="$1" out="$2"
  sweep_log "vitest"
  (cd "$fe" && npx vitest run > "$out/vitest.log" 2>&1) || true
  python3 - "$out/vitest.log" <<'PY'
import re, sys
text = re.sub(r"\x1b\[[0-9;]*m", "", open(sys.argv[1], errors="replace").read())
line = next((l for l in text.splitlines()[::-1] if l.strip().startswith("Tests ")), "")
num = lambda word: int((re.search(rf"(\d+) {word}", line) or [0, 0])[1])
print(num("passed"), num("failed") if line else -1)
PY
}
