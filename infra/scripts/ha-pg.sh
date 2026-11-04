#!/usr/bin/env bash
# Postgres adapter for the failover controller (HA-CF-FAILOVER). Every side effect
# infra/scripts/cf_failover.py has goes through here, so the controller itself stays pure.
# Plan: documentation/plans/infra/PLAN-ha-cf-failover-04nov.md section 3.
#
# Commands:
#   observe            key=value lines: self_pg self_streaming self_lsn sync_names peer_slot peer_pg peer_lsn
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
#   prune DAYS         delete moved-aside data directories older than DAYS
#   route local|peer   active-active: point this node's pgbouncer at the local database or the
#                      peer's (rewrites ROUTE_FILE, reloads pgbouncer) and make this node's Redis
#                      the master (local) or a replica of the peer's (peer)
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
#   Active-active only: ROUTE_FILE (pgbouncer [databases] include, in a directory mounted into the
#   pgbouncer container), PGB_LOCAL_HOST (the db service, e.g. db), PGB_ADMIN (prefix running ONE
#   statement on pgbouncer's admin console, e.g. `... psql -h 127.0.0.1 -p 6432 -U <admin>
#   pgbouncer -c`), PGB_DATABASES (the app's database names through pgbouncer, space-separated),
#   REDIS_CLI (prefix running redis-cli against this node's Redis), PEER_REDIS_PORT (6379),
#   PEER_REDIS_HOST (default PEER_HOST: the peer's Redis on its private address)
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
ROUTE_FILE="${ROUTE_FILE:-}"
PGB_LOCAL_HOST="${PGB_LOCAL_HOST:-db}"
PGB_ADMIN="${PGB_ADMIN:-}"
PGB_DATABASES="${PGB_DATABASES:-}"
REDIS_CLI="${REDIS_CLI:-}"
PEER_REDIS_PORT="${PEER_REDIS_PORT:-6379}"
PEER_REDIS_HOST="${PEER_REDIS_HOST:-$PEER_HOST}"

name_ok() { [[ "$1" =~ ^[a-z0-9_-]{1,32}$ ]]; }
name_ok "$NODE_NAME" && name_ok "$PEER_NAME" || { echo "ha-pg: NODE_NAME/PEER_NAME invalid" >&2; exit 2; }
# Values are spliced into conninfo strings and one-line shell scripts: refuse quotes outright.
for v in "$PEER_HOST" "$PEER_PORT" "$REPL_USER" "$PEER_CONNINFO_EXTRA" "$PGDATA" "$ROUTE_FILE" "$PGB_LOCAL_HOST" "$PEER_REDIS_PORT" "$PEER_REDIS_HOST"; do
  case "$v" in *"'"*|*'"'*|*'\'*|*'$'*|*'`'*|*$'\n'*|*$'\r'*) echo "ha-pg: quotes, \$, backslashes and line breaks are not allowed in the HA env" >&2; exit 2 ;; esac
done
case "$PGDATA" in /*/*) ;; *) echo "ha-pg: PGDATA must be a subdirectory of the volume" >&2; exit 2 ;; esac
for v in $PGB_DATABASES; do
  [[ "$v" =~ ^[A-Za-z0-9_]{1,63}$ ]] && [ "$v" != pgbouncer ] \
    || { echo "ha-pg: PGB_DATABASES must be plain app database names (not pgbouncer)" >&2; exit 2; }
done
# Hosts and ports go into a pgbouncer connect string and a REPLICAOF: a space would add keys
# (review N3), so only a plain host name / address and digits are accepted.
for v in "$PEER_HOST" "$PGB_LOCAL_HOST" "$PEER_REDIS_HOST"; do
  [[ "$v" =~ ^[A-Za-z0-9.-]+$ ]] || { echo "ha-pg: host values must be a plain name or address" >&2; exit 2; }
done
for v in "$PEER_PORT" "$PEER_REDIS_PORT"; do
  [[ "$v" =~ ^[0-9]{1,5}$ ]] || { echo "ha-pg: ports must be digits" >&2; exit 2; }
done

SELF_SLOT=${NODE_NAME//-/_}
PEER_SLOT=${PEER_NAME//-/_}
PEER_CONNINFO="host=$PEER_HOST port=$PEER_PORT user=$REPL_USER dbname=postgres connect_timeout=3 $PEER_CONNINFO_EXTRA"
STANDBY_CONNINFO="host=$PEER_HOST port=$PEER_PORT user=$REPL_USER application_name=$NODE_NAME $PEER_CONNINFO_EXTRA"

# shellcheck disable=SC2086
local_sql() { timeout 20 $PG_EXEC psql -XAtq -F'|' -d postgres -v ON_ERROR_STOP=1 -c "$1"; }
# shellcheck disable=SC2086
offline() { $PG_OFFLINE_SH "$1"; }
# Whole commands (they may hold a pipe) run through sh -c; PG_EXEC / PG_OFFLINE_SH are prefixes.
running() { sh -c "$PG_RUNNING" >/dev/null 2>&1; }
pg_start() { sh -c "$PG_START"; }
pg_stop() { sh -c "$PG_STOP"; }

SELF_SQL="SELECT CASE WHEN pg_is_in_recovery() THEN 'standby' ELSE 'primary' END,
  (CASE WHEN pg_is_in_recovery()
        THEN pg_wal_lsn_diff(coalesce(greatest(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()), '0/0'), '0/0')
        ELSE pg_wal_lsn_diff(pg_current_wal_lsn(), '0/0') END)::bigint,
  (CASE WHEN pg_is_in_recovery()
        THEN EXISTS (SELECT 1 FROM pg_stat_wal_receiver WHERE status = 'streaming')
        ELSE EXISTS (SELECT 1 FROM pg_stat_replication WHERE application_name = '$PEER_NAME' AND state = 'streaming') END),
  replace(current_setting('synchronous_standby_names'), '\"', ''),
  (CASE WHEN pg_is_in_recovery() THEN true
        ELSE EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = '$PEER_SLOT' AND coalesce(wal_status, '') <> 'lost') END)"
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
      IFS='|' read -r role lsn streaming sync slot <<<"$out"
      echo "self_pg=$role"; echo "self_lsn=$lsn"; echo "self_streaming=$streaming"; echo "sync_names=$sync"
      echo "peer_slot=$slot"
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
    route=""
    if [ -n "$ROUTE_FILE" ] && [ -f "$ROUTE_FILE" ]; then
      route=$(sed -n '1s/^; route=\(local\|peer\)\b.*/\1/p' "$ROUTE_FILE")
    fi
    echo "route=$route"
    redis_role=""
    if [ -n "$REDIS_CLI" ]; then
      # shellcheck disable=SC2086
      redis_role=$(timeout 5 $REDIS_CLI ROLE 2>/dev/null | head -1 | tr -d '\r')
      case "$redis_role" in master|slave) ;; *) redis_role="" ;; esac
    fi
    echo "redis_role=$redis_role"
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
  route)
    target="${2:-}"
    [ -n "$ROUTE_FILE" ] || { echo "ha-pg: ROUTE_FILE unset (active-active only)" >&2; exit 2; }
    case "$target" in
      local) host=$PGB_LOCAL_HOST; port=5432 ;;
      peer) host=$PEER_HOST; port=$PEER_PORT ;;
      *) echo "ha-pg: route local|peer" >&2; exit 2 ;;
    esac
    # Redis FIRST: a node coming back starts its Redis as a (stale) master; it must be a replica
    # of the peer before pgbouncer makes this node's app healthy again, or its app would write to
    # the stale Redis for a moment (drill finding, active-active round 1).
    redis_failed=0
    if [ -n "$REDIS_CLI" ]; then
      if [ "$target" = local ]; then
        # shellcheck disable=SC2086
        timeout 10 $REDIS_CLI REPLICAOF NO ONE >/dev/null || redis_failed=1
        # A new primary's database matters more than its Redis: re-point pgbouncer anyway (its
        # lease needs a healthy origin) and report the failure; R1 retries Redis by its role.
        [ "$redis_failed" = 0 ] || echo "ha-pg: redis REPLICAOF NO ONE failed; re-pointing pgbouncer anyway" >&2
      else
        # shellcheck disable=SC2086
        timeout 10 $REDIS_CLI REPLICAOF "$PEER_REDIS_HOST" "$PEER_REDIS_PORT" >/dev/null \
          || { echo "ha-pg: redis REPLICAOF peer failed; pgbouncer left as it is" >&2; exit 1; }
      fi
    fi
    # Same target, already confirmed (R1 only had to repair the Redis role): leave pgbouncer
    # alone, a reload + KILL would cut every app connection for nothing.
    want="* = host=$host port=$port"
    if [ -f "$ROUTE_FILE" ] && head -1 "$ROUTE_FILE" | grep -q "^; route=$target " \
       && grep -qxF "$want" "$ROUTE_FILE"; then
      [ "$redis_failed" = 0 ] || exit 1
      exit 0
    fi
    # The file says "unconfirmed" until pgbouncer has taken it (review blocker 1b): if the reload
    # fails, observe reports no route and R1 retries next tick instead of trusting the file.
    tmp=$(mktemp "$ROUTE_FILE.XXXXXX") || exit 1
    printf '; route=unconfirmed (written by ha-pg.sh route; do not edit)\n[databases]\n* = host=%s port=%s\n' \
      "$host" "$port" > "$tmp" && chmod 0644 "$tmp" && mv -f "$tmp" "$ROUTE_FILE" || { rm -f "$tmp"; exit 1; }
    # RELOAD reads the new target. Then KILL + RESUME each app database: that drops every client
    # and server connection so the app reconnects through the new target, in ANY pool mode. In
    # session mode RECONNECT alone would wait for the app to release its pooled connections,
    # which it never does, and a connection pinned to a running standby would stay there
    # (review round 2 blocker 1). A route change never moves away from the writable primary,
    # so the dropped connections were not doing useful writes.
    [ -n "$PGB_ADMIN" ] || { echo "ha-pg: PGB_ADMIN unset" >&2; exit 2; }
    # shellcheck disable=SC2086
    timeout 15 $PGB_ADMIN "RELOAD" >/dev/null || { echo "ha-pg: pgbouncer RELOAD failed; route left unconfirmed" >&2; exit 1; }
    for db in $PGB_DATABASES; do
      # KILL pauses the database until RESUME, so RESUME ALWAYS runs, whatever KILL returned
      # (a KILL may have taken effect even if psql timed out). With the `*` wildcard, KILL of a
      # database with no pool yet succeeds (checked on pgbouncer 1.23), so ANY KILL failure
      # (timeout, exec, auth) leaves the route unconfirmed and R1 retries (review round 3).
      # The only harmless RESUME failure is "is not paused".
      # shellcheck disable=SC2086
      kout=$(timeout 15 $PGB_ADMIN "KILL $db" 2>&1); krc=$?
      # shellcheck disable=SC2086
      rout=$(timeout 15 $PGB_ADMIN "RESUME $db" 2>&1); rrc=$?
      if [ "$rrc" != 0 ]; then
        case "$rout" in
          *"is not paused"*) ;;
          *) echo "ha-pg: pgbouncer RESUME $db FAILED (database may be paused); route left unconfirmed" >&2; exit 1 ;;
        esac
      fi
      if [ "$krc" != 0 ]; then
        echo "ha-pg: pgbouncer KILL $db failed (${kout##*$'\n'}); route left unconfirmed" >&2
        exit 1
      fi
    done
    tmp=$(mktemp "$ROUTE_FILE.XXXXXX") || exit 1
    sed "1s/^; route=unconfirmed /; route=$target /" "$ROUTE_FILE" > "$tmp" && chmod 0644 "$tmp" && mv -f "$tmp" "$ROUTE_FILE" \
      || { rm -f "$tmp"; exit 1; }
    [ "$redis_failed" = 0 ] || exit 1
    ;;
  prune)
    days="${2:-7}"
    [[ "$days" =~ ^[0-9]+$ ]] || exit 2
    running || exit 0
    parent=$(dirname "$PGDATA"); base=$(basename "$PGDATA")
    # shellcheck disable=SC2086
    $PG_EXEC find "$parent" -maxdepth 1 -type d -name "$base.old-*" -mtime +"$days" -exec rm -rf {} +
    ;;
  *)
    echo "usage: ha-pg.sh observe|role|fence|promote|ensure-slot|start-standby|rejoin [reseed]|set-sync NAMES|route local|peer|prune DAYS" >&2
    exit 2
    ;;
esac
