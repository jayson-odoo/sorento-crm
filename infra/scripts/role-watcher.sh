#!/usr/bin/env bash
# Role watcher (HA-TIER1-N8N-BOX). Runs on BOTH CRM nodes as a systemd service.
# Plan: documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md section 2 "role watcher".
#
# Workers and the scheduler must run only on the node whose Postgres is the Patroni leader.
# Every INTERVAL seconds it asks the LOCAL Patroni (GET /primary: 200 only on the leader).
# After CONFIRM readings in a row:
#   leader:     start the worker services if fewer than all are running (--no-deps, so the
#               Patroni `db` and pgbouncer are never recreated by this script, and
#               --no-recreate, so a running worker is never touched). They start on the image
#               tag the last HA deploy recorded in $PROJECT_DIR/.ha-image-tag; with none
#               recorded nothing is started (a replica still stops).
#   not leader: stop them, every tick (stop is idempotent, so an unreadable `ps` or a worker
#               stuck restarting can never leave one running on a replica).
# Patroni unreachable counts as "not leader": a leader whose Patroni died loses its key anyway.
#
# While the deploy lock (DEPLOY_LOCK_PATH, same file as scripts/blue_green_deploy.sh) is held, the
# whole tick is skipped: neither start nor stop, so it never races a deploy's worker recreate.
#
# Env (all optional): PATRONI_URL, INTERVAL, CONFIRM, SERVICES, COMPOSE_FILES, PROJECT_DIR,
# DEPLOY_LOCK_PATH,
# MAX_TICKS (tests: stop after N ticks; 0 = forever).
set -uo pipefail

PATRONI_URL="${PATRONI_URL:-http://127.0.0.1:8008/primary}"
INTERVAL="${INTERVAL:-5}"
CONFIRM="${CONFIRM:-2}"
SERVICES="${SERVICES:-worker worker_fast}"
COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.yml -f compose.ha.yml}"
PROJECT_DIR="${PROJECT_DIR:-.}"
MAX_TICKS="${MAX_TICKS:-0}"
DEPLOY_LOCK_PATH="${DEPLOY_LOCK_PATH:-/opt/sorento-crm2/.deploy.lock}"

cd "$PROJECT_DIR" || { echo "role-watcher: cannot cd to $PROJECT_DIR" >&2; exit 1; }

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) role-watcher: $*"; }

compose() {
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES --profile promoted "$@"
}

# True while a deploy (or the restore test) holds the deploy lock. No lock file: not held.
deploy_lock_held() {
  [ -r "$DEPLOY_LOCK_PATH" ] || return 1
  ( exec 8<"$DEPLOY_LOCK_PATH"; flock -n 8 ) && return 1
  return 0
}

is_leader() {
  local code
  code=$(curl -s -o /dev/null -m 3 -w '%{http_code}' "$PATRONI_URL" 2>/dev/null) || code=000
  [ "$code" = "200" ]
}

# How many of SERVICES are running now; -1 when compose cannot tell.
running_count() {
  local out
  # shellcheck disable=SC2086
  out=$(compose ps --status running -q $SERVICES 2>/dev/null) || { echo -1; return; }
  printf '%s\n' "$out" | grep -c . || true
}

want_count=$(echo "$SERVICES" | wc -w)
streak_role=""
streak=0
ticks=0
while :; do
  if deploy_lock_held; then
    log "deploy lock held, skipping this tick"
    ticks=$((ticks + 1))
    if [ "$MAX_TICKS" -gt 0 ] && [ "$ticks" -ge "$MAX_TICKS" ]; then exit 0; fi
    sleep "$INTERVAL"
    continue
  fi
  if is_leader; then role=leader; else role=follower; fi
  if [ "$role" = "$streak_role" ]; then streak=$((streak + 1)); else streak_role=$role; streak=1; fi

  if [ "$streak" -ge "$CONFIRM" ]; then
    running=$(running_count)
    if [ "$role" = leader ]; then
      if [ "$running" -lt "$want_count" ]; then
        tag=$(head -n 1 "$PWD/.ha-image-tag" 2>/dev/null || true)
        if [ -z "$tag" ]; then
          log "local Postgres leads but no image tag is recorded in $PWD/.ha-image-tag: not starting $SERVICES"
        else
          log "local Postgres leads: starting $SERVICES on $tag (running: $running)"
          # shellcheck disable=SC2086
          IMAGE_TAG="$tag" compose up -d --no-deps --no-recreate $SERVICES || log "start failed; retrying next tick"
        fi
      fi
    else
      [ "$running" != "0" ] && log "local Postgres does not lead: stopping $SERVICES (running: $running)"
      # shellcheck disable=SC2086
      compose stop $SERVICES >/dev/null 2>&1 || log "stop failed; retrying next tick"
    fi
  fi

  ticks=$((ticks + 1))
  if [ "$MAX_TICKS" -gt 0 ] && [ "$ticks" -ge "$MAX_TICKS" ]; then exit 0; fi
  sleep "$INTERVAL"
done
