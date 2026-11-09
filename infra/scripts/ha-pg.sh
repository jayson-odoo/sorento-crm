#!/usr/bin/env bash
# Postgres adapter for the failover controller (HA-CF-FAILOVER). Every side effect
# infra/scripts/cf_failover.py has goes through here, so the controller itself stays pure.
# Plan: documentation/plans/infra/PLAN-ha-cf-failover-04nov.md section 3.
#
# Commands:
#   observe            key=value lines: self_pg self_streaming self_lsn sync_names peer_slot peer_flush_lsn peer_pg peer_lsn
#                      (peer_flush_lsn: primary only, the sync standby's flush position, write position
#                      under SYNC_MODE=remote_write; empty when it has no row)
#   role               primary | standby | down (local only; the role watcher reads this)
#   (observe prints self_pg=unknown when psql fails but the container runs: not "down")
#   fence              stop Postgres FIRST (workers cannot write without it), mark it a standby
#                      (standby.signal: any later start, even a manual one, comes up read-only),
#                      then stop the workers fast
#   promote            pg_promote(), then (re)create the peer's replication slot
#   start-standby      start a stopped Postgres AS A STANDBY (standby.signal first); no-op if running
#   rejoin [reseed]    pg_rewind onto the peer; if that fails (or `reseed`), move PGDATA aside and
#                      pg_basebackup; a failed copy puts the old directory back.
#                      exit 0 = rewound, 3 = re-seeded, other = failed
#   ensure-slot        on the primary: (re)create the peer's replication slot if missing or lost
#   set-sync NAMES     synchronous_standby_names (empty = async), synchronous_commit from SYNC_MODE
#   sync-record get    key=value lines rec_mode rec_primary rec_since from the R2 sync record (exit 1 = unreadable)
#   sync-record put M  write {mode M (sync|async), primary NODE_NAME, since now} to R2 (exit 1 = failed)
#   prune DAYS         delete moved-aside data directories older than DAYS
#
# Env (the same file on both nodes except the names and PEER_HOST):
#   NODE_NAME PEER_NAME PEER_HOST [PEER_PORT=5432] [REPL_USER=replicator] [PEER_CONNINFO_EXTRA]
#   PGDATA                 data directory INSIDE the container; must be a subdirectory of the volume
#                          (e.g. /var/lib/postgresql/data/pgdata) so a re-seed can move it aside
#   PG_EXEC                prefix running a command in the RUNNING db container as postgres
#   PG_RUNNING             command (run by sh -c) that succeeds when the db container is running
#   PG_START / PG_STOP     commands (sh -c) that start / stop the db container (never recreate it)
#   PG_OFFLINE_SH          prefix taking ONE shell script, run as postgres with the data volume
#                          mounted while the db container is stopped, able to reach the peer
#   PEER_PSQL              psql that reaches the peer over the private link (host client)
#   WORKERS_STOP           command (sh -c) that stops worker + worker_fast (the role watcher would stop them a tick later)
#   SYNC_MODE              off | remote_write | on_commit
#   SELF_APP_NAME PEER_APP_NAME   application_name of this / the peer standby (default NODE_NAME / PEER_NAME)
#   SELF_SLOT PEER_SLOT           replication slot names (default NODE_NAME / PEER_NAME, dashes to underscores)
#   R2_ENDPOINT R2_BUCKET R2_CREDENTIALS_FILE [SYNC_RECORD_KEY]   sync record (https, or http://127.0.0.1 for tests)
# Passwords: never in this env. The replication user's password sits in a pgpass file read by
# both the container and the host client (PGPASSFILE), mode 600.
set -uo pipefail

: "${NODE_NAME:?}" "${PEER_NAME:?}" "${PEER_HOST:?}" "${PGDATA:?}" "${PG_EXEC:?}" "${PG_RUNNING:?}"
: "${PG_START:?}" "${PG_STOP:?}" "${PG_OFFLINE_SH:?}"
PEER_PORT="${PEER_PORT:-5432}"
REPL_USER="${REPL_USER:-replicator}"
PEER_CONNINFO_EXTRA="${PEER_CONNINFO_EXTRA:-}"
PEER_PSQL="${PEER_PSQL:-psql}"
WORKERS_STOP="${WORKERS_STOP:-true}"
SYNC_MODE="${SYNC_MODE:-off}"

name_ok() { [[ "$1" =~ ^[a-z0-9_-]{1,32}$ ]]; }
name_ok "$NODE_NAME" && name_ok "$PEER_NAME" || { echo "ha-pg: NODE_NAME/PEER_NAME invalid" >&2; exit 2; }
# Values are spliced into conninfo strings and one-line shell scripts: refuse quotes outright.
for v in "$PEER_HOST" "$PEER_PORT" "$REPL_USER" "$PEER_CONNINFO_EXTRA" "$PGDATA"; do
  case "$v" in *"'"*|*'"'*|*'\'*|*'$'*|*'`'*|*$'\n'*|*$'\r'*) echo "ha-pg: quotes, \$, backslashes and line breaks are not allowed in the HA env" >&2; exit 2 ;; esac
done
case "$PGDATA" in /*/*) ;; *) echo "ha-pg: PGDATA must be a subdirectory of the volume" >&2; exit 2 ;; esac

SELF_APP_NAME="${SELF_APP_NAME:-$NODE_NAME}"; PEER_APP_NAME="${PEER_APP_NAME:-$PEER_NAME}"
SELF_SLOT="${SELF_SLOT:-${NODE_NAME//-/_}}"; PEER_SLOT="${PEER_SLOT:-${PEER_NAME//-/_}}"
name_ok "$SELF_APP_NAME" && name_ok "$PEER_APP_NAME" || { echo "ha-pg: app name invalid" >&2; exit 2; }
slot_ok() { [[ "$1" =~ ^[a-z0-9_]{1,63}$ ]]; }
slot_ok "$SELF_SLOT" && slot_ok "$PEER_SLOT" || { echo "ha-pg: slot invalid" >&2; exit 2; }
PEER_CONNINFO="host=$PEER_HOST port=$PEER_PORT user=$REPL_USER dbname=postgres connect_timeout=3 $PEER_CONNINFO_EXTRA"
STANDBY_CONNINFO="host=$PEER_HOST port=$PEER_PORT user=$REPL_USER application_name=$SELF_APP_NAME $PEER_CONNINFO_EXTRA"

# shellcheck disable=SC2086
local_sql() { timeout 20 $PG_EXEC psql -XAtq -F'|' -d postgres -v ON_ERROR_STOP=1 -c "$1"; }
# shellcheck disable=SC2086
offline() { $PG_OFFLINE_SH "$1"; }
# Whole commands (they may hold a pipe) run through sh -c; PG_EXEC / PG_OFFLINE_SH are prefixes.
running() { sh -c "$PG_RUNNING" >/dev/null 2>&1; }
pg_start() { sh -c "$PG_START"; }
pg_stop() { sh -c "$PG_STOP"; }

# The sync standby's acknowledged position: write_lsn is what remote_write waits for, else flush_lsn.
PEER_ACK_COL=flush_lsn; [ "${SYNC_MODE:-off}" = remote_write ] && PEER_ACK_COL=write_lsn
SELF_SQL="SELECT CASE WHEN pg_is_in_recovery() THEN 'standby' ELSE 'primary' END,
  (CASE WHEN pg_is_in_recovery()
        THEN pg_wal_lsn_diff(coalesce(greatest(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()), '0/0'), '0/0')
        ELSE pg_wal_lsn_diff(pg_current_wal_lsn(), '0/0') END)::bigint,
  (CASE WHEN pg_is_in_recovery()
        THEN EXISTS (SELECT 1 FROM pg_stat_wal_receiver WHERE status = 'streaming')
        ELSE EXISTS (SELECT 1 FROM pg_stat_replication WHERE application_name = '$PEER_APP_NAME' AND state = 'streaming') END),
  replace(current_setting('synchronous_standby_names'), '\"', ''),
  (CASE WHEN pg_is_in_recovery() THEN true
        ELSE EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = '$PEER_SLOT' AND coalesce(wal_status, '') <> 'lost') END),
  (CASE WHEN pg_is_in_recovery() THEN NULL
        ELSE (SELECT max(pg_wal_lsn_diff($PEER_ACK_COL, '0/0'))::bigint FROM pg_stat_replication WHERE application_name = '$PEER_APP_NAME') END)"
PEER_SQL="SELECT CASE WHEN pg_is_in_recovery() THEN 'standby' ELSE 'primary' END,
  (CASE WHEN pg_is_in_recovery()
        THEN pg_wal_lsn_diff(coalesce(greatest(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()), '0/0'), '0/0')
        ELSE pg_wal_lsn_diff(pg_current_wal_lsn(), '0/0') END)::bigint"

self_role() {
  local out
  if out=$(local_sql "SELECT CASE WHEN pg_is_in_recovery() THEN 'standby' ELSE 'primary' END" 2>/dev/null) && [ -n "$out" ]; then
    echo "$out"
  else
    echo down
  fi
}

# Recovery settings written after a rewind or re-seed: both copy the SOURCE's
# postgresql.auto.conf, whose primary_conninfo / slot point the wrong way. Appended lines win.
standby_conf_script() {
  local conf="$PGDATA/postgresql.auto.conf"
  echo "echo \"primary_conninfo = '$STANDBY_CONNINFO'\" >> '$conf' && echo \"primary_slot_name = '$SELF_SLOT'\" >> '$conf' && echo \"synchronous_standby_names = ''\" >> '$conf' && touch '$PGDATA/standby.signal'"
}

cmd="${1:-}"
case "$cmd" in
  observe)
    if out=$(local_sql "$SELF_SQL" 2>/dev/null) && [ -n "$out" ]; then
      IFS='|' read -r role lsn streaming sync slot flush <<<"$out"
      echo "self_pg=$role"; echo "self_lsn=$lsn"; echo "self_streaming=$streaming"; echo "sync_names=$sync"
      echo "peer_slot=$slot"; echo "peer_flush_lsn=$flush"
    elif running; then
      # Postgres may still be up and taking writes over TCP while `exec psql` fails (wedged
      # dockerd, cgroup pressure). Never call that "down": the controller counts the tick as
      # failed and its failure path fences or lets the watchdog reboot (review round 2).
      # Only a postmaster that refuses every new connection BECAUSE it is recovering or starting
      # is "down": nothing can write then, and fencing it would loop a long recovery. Not "no
      # response" (an overloaded but writable server times out pg_isready) and not a smart
      # shutdown (rejects new connections while old sessions keep committing): both "unknown"
      # (review round 3). pg_controldata opens no connection.
      # shellcheck disable=SC2086
      ready=$(timeout 10 $PG_EXEC pg_isready -d postgres 2>/dev/null || true)
      # shellcheck disable=SC2086
      state=$(timeout 10 $PG_EXEC pg_controldata -D "$PGDATA" 2>/dev/null | sed -n 's/^Database cluster state: *//p' || true)
      case "$ready|$state" in
        *"rejecting connections"*"|in crash recovery"|*"rejecting connections"*"|in archive recovery"|*"rejecting connections"*"|starting up")
          echo "self_pg=down"; echo "self_streaming=f"; echo "self_lsn="; echo "sync_names="; echo "peer_slot=t" ;;
        *) echo "self_pg=unknown" ;;
      esac
    else
      echo "self_pg=down"; echo "self_streaming=f"; echo "self_lsn="; echo "sync_names="; echo "peer_slot=t"
    fi
    # A peer that accepts the connection and then stalls must not hang the tick (review S3).
    # shellcheck disable=SC2086
    if out=$(timeout 8 $PEER_PSQL -XAtq -F'|' "$PEER_CONNINFO options=-cstatement_timeout=5000" -c "$PEER_SQL" 2>/dev/null) && [ -n "$out" ]; then
      IFS='|' read -r prole plsn <<<"$out"
      echo "peer_pg=$prole"; echo "peer_lsn=$plsn"
    else
      echo "peer_pg=unreachable"; echo "peer_lsn="
    fi
    ;;
  role)
    self_role
    ;;
  fence)
    pg_stop || { echo "ha-pg: stopping Postgres FAILED" >&2; exit 1; }
    offline "touch '$PGDATA/standby.signal'" || echo "ha-pg: could not write standby.signal" >&2
    sh -c "$WORKERS_STOP" || echo "ha-pg: stopping the workers failed (they cannot write: Postgres is stopped)" >&2
    ;;
  promote)
    [ "$(self_role)" = standby ] || { echo "ha-pg: not a standby, refusing to promote" >&2; exit 1; }
    local_sql "SELECT pg_promote(true, 60)" | grep -qx t || { echo "ha-pg: pg_promote did not finish" >&2; exit 1; }
    # Slots are not replicated: a stale or invalidated copy would refuse the peer, so recreate it.
    local_sql "SELECT pg_drop_replication_slot(slot_name) FROM pg_replication_slots WHERE slot_name IN ('$PEER_SLOT', '$SELF_SLOT') AND NOT active" >/dev/null
    local_sql "SELECT pg_create_physical_replication_slot('$PEER_SLOT', true)" >/dev/null
    ;;
  ensure-slot)
    [ "$(self_role)" = primary ] || exit 0
    local_sql "SELECT pg_drop_replication_slot(slot_name) FROM pg_replication_slots WHERE slot_name = '$PEER_SLOT' AND wal_status = 'lost' AND NOT active" >/dev/null
    local_sql "SELECT pg_create_physical_replication_slot('$PEER_SLOT', true) WHERE NOT EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = '$PEER_SLOT')" >/dev/null
    ;;
  start-standby)
    if running; then exit 0; fi
    offline "touch '$PGDATA/standby.signal'" || exit 1
    pg_start
    ;;
  rejoin)
    running && { pg_stop || exit 1; }
    if [ "${2:-}" != reseed ] && offline "pg_rewind -D '$PGDATA' --source-server='$PEER_CONNINFO' --write-recovery-conf"; then
      offline "$(standby_conf_script)" || exit 1
      pg_start || exit 1
      exit 0
    fi
    echo "ha-pg: re-seeding from the peer (old data kept aside)" >&2
    ts=$(date -u +%Y%m%dT%H%M%SZ)
    old="$PGDATA.old-$ts"
    # A failed copy removes the partial directory and puts the old one back, so a flaky link
    # never piles up copies (review S5).
    offline "mv '$PGDATA' '$old' && { pg_basebackup -D '$PGDATA' -d '$PEER_CONNINFO' -X stream -c fast || { rm -rf '$PGDATA'; mv '$old' '$PGDATA'; exit 1; }; }" || exit 1
    offline "$(standby_conf_script)" || exit 1
    pg_start || exit 1
    exit 3
    ;;
  set-sync)
    names="${2-}"
    if [ -n "$names" ]; then
      name_ok "$names" || { echo "ha-pg: bad standby name" >&2; exit 2; }
      commit=on; [ "$SYNC_MODE" = remote_write ] && commit=remote_write
      local_sql "ALTER SYSTEM SET synchronous_commit = '$commit'" >/dev/null || exit 1
      local_sql "ALTER SYSTEM SET synchronous_standby_names = '\"$names\"'" >/dev/null || exit 1
    else
      local_sql "ALTER SYSTEM SET synchronous_standby_names = ''" >/dev/null || exit 1
    fi
    local_sql "SELECT pg_reload_conf()" >/dev/null
    ;;
  sync-record)
    [ -n "${R2_ENDPOINT:-}" ] && [ -n "${R2_BUCKET:-}" ] && [ -n "${R2_CREDENTIALS_FILE:-}" ] || exit 2
    [[ "$R2_ENDPOINT" =~ ^(https://[A-Za-z0-9.-]+(:[0-9]+)?|http://127\.0\.0\.1(:[0-9]+)?)(/.*)?$ ]] || exit 2
    rec_key="${SYNC_RECORD_KEY:-ha/sync-state.json}"
    [[ "$R2_BUCKET" =~ ^[a-z0-9._-]{1,200}$ && "$rec_key" =~ ^[a-z0-9._/-]{1,200}$ ]] || exit 2
    url="$R2_ENDPOINT/$R2_BUCKET/$rec_key"
    # First match only: a duplicated key line must not become a multi-line value.
    id=$(sed -n 's/^AWS_ACCESS_KEY_ID=//p' "$R2_CREDENTIALS_FILE" | head -n 1)
    sec=$(sed -n 's/^AWS_SECRET_ACCESS_KEY=//p' "$R2_CREDENTIALS_FILE" | head -n 1)
    [[ $id =~ ^[A-Za-z0-9]{16,128}$ && $sec =~ ^[A-Za-z0-9/+=]{16,128}$ ]] || exit 2
    cfg() { printf 'user = "%s:%s"\n' "$id" "$sec"; }
    # -q first: no ~/.curlrc; the credentials reach curl on stdin only, never on argv.
    r2curl() { cfg | curl -q --proto =https,http -fsS -m 5 -K - --aws-sigv4 "aws:amz:auto:s3" "$@"; }
    case "${2:-}" in
      get)
        body=$(r2curl "$url") || exit 1
        printf '%s' "$body" | python3 -I -c '
import json, re, sys
try:
    d = json.load(sys.stdin)
    ok = (isinstance(d, dict) and d.get("mode") in ("sync", "async")
          and isinstance(d.get("primary"), str) and re.fullmatch(r"[a-z0-9_-]{1,32}", d["primary"])
          and type(d.get("since")) is int and d["since"] >= 0)
except ValueError:
    ok = False
if not ok:
    sys.exit(1)
print("rec_mode=%s\nrec_primary=%s\nrec_since=%d" % (d["mode"], d["primary"], d["since"]))' || exit 1 ;;
      put)
        m="${3:-}"; [ "$m" = sync ] || [ "$m" = async ] || exit 2
        code=$(r2curl -o /dev/null -w '%{http_code}' -X PUT -H 'Content-Type: application/json' --data "{\"mode\": \"$m\", \"primary\": \"$NODE_NAME\", \"since\": $(date +%s)}" "$url") || exit 1
        [ "$code" = 200 ] || exit 1 ;;
      *) exit 2 ;;
    esac ;;
  prune)
    days="${2:-7}"
    [[ "$days" =~ ^[0-9]+$ ]] || exit 2
    running || exit 0
    parent=$(dirname "$PGDATA"); base=$(basename "$PGDATA")
    # shellcheck disable=SC2086
    $PG_EXEC find "$parent" -maxdepth 1 -type d -name "$base.old-*" -mtime +"$days" -exec rm -rf {} +
    ;;
  *)
    echo "usage: ha-pg.sh observe|role|fence|promote|ensure-slot|start-standby|rejoin [reseed]|set-sync NAMES|prune DAYS" >&2
    exit 2
    ;;
esac
