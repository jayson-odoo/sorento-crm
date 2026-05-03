#!/usr/bin/env bash
# Profile the backend Python process during a stress run.
#
# Usage:
#   ./ci/profile-backend.sh top              # live top during stress (5s refresh)
#   ./ci/profile-backend.sh record <secs>    # record flamegraph for N seconds
#   ./ci/profile-backend.sh dump             # dump current stack of every worker
#
# Examples:
#   # Terminal 1: start a stress run
#   K6_PEAK_RPS=50 K6_HOLD_MIN=3 ./ci/run.sh load backend/listings_read
#   # Terminal 2: profile a worker
#   ./ci/profile-backend.sh top
#   ./ci/profile-backend.sh record 60
#
# Requires py-spy in the backend container. Auto-installs on first run.

set -euo pipefail

CONTAINER="${BACKEND_CONTAINER:-sorento_crm_backend}"
MODE="${1:-top}"
DURATION="${2:-30}"

ensure_pyspy() {
  if ! docker exec "$CONTAINER" sh -c 'command -v py-spy >/dev/null 2>&1'; then
    echo "[profile] py-spy not present, installing..."
    docker exec "$CONTAINER" pip install --quiet py-spy 2>&1 | tail -3
  fi
}

# Find a single gunicorn worker pid (any worker, not master).
find_worker_pid() {
  docker exec "$CONTAINER" sh -c '
    for f in /proc/[0-9]*/cmdline; do
      pid=$(echo "$f" | sed "s|/proc/||;s|/cmdline||")
      cmd=$(tr "\0" " " < "$f" 2>/dev/null)
      case "$cmd" in
        *gunicorn*master*) ;;
        *gunicorn*"app.main:app"*) echo "$pid"; break ;;
      esac
    done
  '
}

list_worker_pids() {
  docker exec "$CONTAINER" sh -c '
    for f in /proc/[0-9]*/cmdline; do
      pid=$(echo "$f" | sed "s|/proc/||;s|/cmdline||")
      cmd=$(tr "\0" " " < "$f" 2>/dev/null)
      case "$cmd" in
        *gunicorn*master*) ;;
        *gunicorn*"app.main:app"*) echo "$pid" ;;
      esac
    done
  '
}

ensure_pyspy
PID=$(find_worker_pid)

if [[ -z "$PID" ]]; then
  echo "[profile] no gunicorn worker pid found in $CONTAINER" >&2
  exit 1
fi

echo "[profile] container=$CONTAINER worker_pid=$PID mode=$MODE"

case "$MODE" in
  top)
    docker exec -it "$CONTAINER" py-spy top --pid "$PID"
    ;;
  record)
    OUT="profile-${PID}-$(date -u +%Y%m%dT%H%M%SZ).svg"
    echo "[profile] recording ${DURATION}s -> ${OUT}"
    docker exec "$CONTAINER" py-spy record \
      --pid "$PID" \
      --duration "$DURATION" \
      --output "/tmp/${OUT}" \
      --rate 100
    docker cp "${CONTAINER}:/tmp/${OUT}" "results/${OUT}"
    echo "[profile] saved -> results/${OUT}  (open in browser)"
    ;;
  dump)
    PIDS=$(list_worker_pids)
    for p in $PIDS; do
      echo "=== worker pid=$p ==="
      docker exec "$CONTAINER" py-spy dump --pid "$p" 2>&1 | head -60
      echo
    done
    ;;
  *)
    echo "usage: $0 [top|record <secs>|dump]" >&2
    exit 1
    ;;
esac
