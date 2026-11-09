#!/usr/bin/env bash
# HA health checks + cheap self-healing (HA-CF-FAILOVER). Cron every 5 minutes on both CRM
# nodes. Plan: documentation/plans/infra/PLAN-ha-cf-failover-04nov.md (sections 2 and 3).
#
# Pings HC_URL (Healthchecks.io) on success, HC_URL/fail with the reasons otherwise, so alerts
# come from outside our servers. Unset HC_URL = print only.
#
# Checks: disk use (and prune of old pre-migrate dumps past PRUNE_AT_PCT); the two nodes' roles
# (exactly one primary; read with `ha-pg.sh observe`, which also reads the peer over the link);
# clock NTP-synced (the controller's windows are wall-clock seconds); the shared config files
# identical on both nodes (hashes only, never contents); and on the primary: the standby
# streaming, its byte lag, WAL archiving fresh and not failing, pg_wal size, newest WAL-G base
# backup age. EXPECT_REPLICAS=0 while node A runs alone (before node B exists).
# Cron runs from $HOME, so it cd's to PROJECT_DIR first (compose files are relative).
set -uo pipefail

HC_URL="${HC_URL:-}"
DATA_PATH="${DATA_PATH:-/}"
ALERT_AT_PCT="${ALERT_AT_PCT:-80}"
PRUNE_AT_PCT="${PRUNE_AT_PCT:-85}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-/opt/sorento-crm2/backups/pre-migrate}"
SNAPSHOT_KEEP="${SNAPSHOT_KEEP:-2}"
EXPECT_REPLICAS="${EXPECT_REPLICAS:-1}"
MAX_LAG_BYTES="${MAX_LAG_BYTES:-8388608}"          # half of the controller's MAX_LAG
MAX_ARCHIVE_AGE_S="${MAX_ARCHIVE_AGE_S:-600}"
MAX_WAL_BYTES="${MAX_WAL_BYTES:-10737418240}"      # 10 GB
MAX_BACKUP_AGE_S="${MAX_BACKUP_AGE_S:-93600}"      # 26 h
PROJECT_DIR="${PROJECT_DIR:-/opt/sorento-crm2}"
COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.yml -f compose.ha.yml}"
DB_SERVICE="${DB_SERVICE:-db}"
OBSERVE_CMD="${OBSERVE_CMD:-$(cd "$(dirname "$0")" && pwd)/ha-pg.sh observe}"
CLOCK_CMD="${CLOCK_CMD:-timedatectl show -p NTPSynchronized --value}"
# Files that must be byte-identical on both nodes (per-node values live in ha-pg.env only).
SHARED_FILES="${SHARED_FILES:-.env .deploy.env docker-compose.yml compose.ha.yml}"
# Prints `sha256sum` lines for SHARED_FILES on the peer (e.g. ssh over the private link with a
# key whose forced command is that sha256sum). Unset = the comparison is skipped.
PEER_HASH_CMD="${PEER_HASH_CMD:-}"

cd "$PROJECT_DIR" || { echo "ha-checks: cannot cd to $PROJECT_DIR" >&2; exit 2; }

problems=()
note() { problems+=("$1"); }

# One value from the local Postgres (as the postgres superuser, inside the db container).
sql() {
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES exec -T "$DB_SERVICE" psql -U postgres -d postgres -Atc "$1" 2>/dev/null
}

disk_pct() { df -P "$DATA_PATH" | awk 'NR==2 { gsub("%", "", $5); print $5 }'; }

# 1. Disk, with the one self-heal that is always safe: drop the oldest pre-migrate dumps.
pct=$(disk_pct)
if [ -n "$pct" ] && [ "$pct" -ge "$PRUNE_AT_PCT" ] && [ -d "$SNAPSHOT_DIR" ]; then
  # shellcheck disable=SC2012
  ls -1t "$SNAPSHOT_DIR"/pre-migrate-*.dump 2>/dev/null | tail -n +"$((SNAPSHOT_KEEP + 1))" | while read -r old; do
    rm -f -- "$old" && echo "pruned $old"
  done
  pct=$(disk_pct)
fi
if [ -z "$pct" ]; then note "disk: df failed"; elif [ "$pct" -ge "$ALERT_AT_PCT" ]; then note "disk ${pct}% used"; fi

# 2. Roles: exactly one primary across the two nodes.
# shellcheck disable=SC2086
obs=$($OBSERVE_CMD 2>/dev/null)
get() { printf '%s\n' "$obs" | sed -n "s/^$1=//p" | head -1; }
self_pg=$(get self_pg); peer_pg=$(get peer_pg); streaming=$(get self_streaming)
case "$self_pg/$peer_pg" in
  primary/primary) note "TWO PRIMARIES" ;;
  standby/standby) note "no primary: both nodes are standby" ;;
  standby/unreachable) note "peer unreachable from the standby" ;;
  down/*) note "local postgres down" ;;
  /*) note "role unreadable" ;;
esac

# 3. Clock: the failover windows are wall-clock seconds.
# shellcheck disable=SC2086
[ "$($CLOCK_CMD 2>/dev/null)" = "yes" ] || note "clock not NTP-synced"

# 4. Shared config identical on both nodes (names only in the alert, never contents).
if [ -n "$PEER_HASH_CMD" ]; then
  # shellcheck disable=SC2086
  mine=$(sha256sum $SHARED_FILES 2>/dev/null)
  # shellcheck disable=SC2086
  if theirs=$($PEER_HASH_CMD 2>/dev/null) && [ -n "$theirs" ]; then
    differ=""
    for f in $SHARED_FILES; do
      a=$(printf '%s\n' "$mine" | awk -v f="$f" '$2 == f { print $1 }')
      b=$(printf '%s\n' "$theirs" | awk -v f="$f" '$2 == f { print $1 }')
      [ -n "$a" ] && [ "$a" = "$b" ] || differ="$differ $f"
    done
    [ -n "$differ" ] && note "config differs between nodes:$differ"
  else
    note "peer config hashes unreadable"
  fi
fi

# 5. Primary-only Postgres checks.
if [ "$self_pg" = "primary" ]; then
  if [ "$EXPECT_REPLICAS" != "0" ] && [ "$streaming" != "t" ]; then note "no replica streaming"; fi
  lag=$(sql "SELECT coalesce(max(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)), 0)::bigint FROM pg_stat_replication")
  if [ -n "$lag" ] && [ "$lag" -gt "$MAX_LAG_BYTES" ]; then note "replica lag ${lag} bytes"; fi
  arch=$(sql "SELECT coalesce(extract(epoch FROM now() - last_archived_time)::bigint, -1) || ' ' || (coalesce(last_failed_time, 'epoch') > coalesce(last_archived_time, 'epoch'))::int FROM pg_stat_archiver")
  read -r arch_age arch_failing <<<"${arch:-"-1 0"}"
  if [ "$arch_age" -lt 0 ] || [ "$arch_age" -gt "$MAX_ARCHIVE_AGE_S" ]; then note "WAL archive stale (${arch_age}s)"; fi
  if [ "${arch_failing:-0}" = "1" ]; then note "WAL archive failing"; fi
  wal=$(sql "SELECT coalesce(sum(size), 0)::bigint FROM pg_ls_waldir()")
  if [ -n "$wal" ] && [ "$wal" -gt "$MAX_WAL_BYTES" ]; then note "pg_wal ${wal} bytes"; fi
  # shellcheck disable=SC2086
  newest=$(docker compose $COMPOSE_FILES exec -T "$DB_SERVICE" wal-g backup-list --json 2>/dev/null \
    | python3 -c 'import json, re, sys, datetime as d
b = json.load(sys.stdin) or []
ages = []
for x in b:
    # wal-g prints Go RFC3339 with up to 9 fractional digits; Python before 3.11 takes 6 at most.
    t = re.sub(r"(\.\d{1,6})\d*", r"\1", x["time"]).replace("Z", "+00:00")
    ages.append((d.datetime.now(d.timezone.utc) - d.datetime.fromisoformat(t)).total_seconds())
print(int(min(ages)) if ages else -1)' 2>/dev/null)
  if [ -z "$newest" ] || [ "$newest" -lt 0 ] || [ "$newest" -gt "$MAX_BACKUP_AGE_S" ]; then note "base backup age ${newest:-unknown}s"; fi
fi

if [ "${#problems[@]}" -eq 0 ]; then
  echo "ha-checks: ok"
  [ -n "$HC_URL" ] && curl -fsS -m 10 --retry 3 -o /dev/null "$HC_URL"
  exit 0
fi
body=$(printf '%s\n' "${problems[@]}")
echo "ha-checks: FAIL"; echo "$body"
[ -n "$HC_URL" ] && curl -fsS -m 10 --retry 3 -o /dev/null --data-raw "$body" "$HC_URL/fail"
exit 1
