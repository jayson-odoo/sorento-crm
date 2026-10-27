#!/usr/bin/env bash
# HA health checks + cheap self-healing (HA-TIER1-N8N-BOX). Cron every 5 minutes on both CRM
# nodes (witness: ETCD_ONLY=1). Plan: documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md
# section 8b.
#
# Pings HC_URL (Healthchecks.io) on success, HC_URL/fail with the reasons otherwise, so alerts
# come from outside our servers. Unset HC_URL = print only.
#
# Checks: disk use (and prune of old pre-migrate dumps past PRUNE_AT_PCT), etcd members healthy,
# exactly one Patroni leader in the cluster, and on the leader: a replica streaming, its byte
# lag, WAL archiving fresh and not failing, pg_wal size, newest WAL-G base backup age.
# Cron runs from $HOME, so it cd's to PROJECT_DIR first (compose files are relative).
set -uo pipefail

HC_URL="${HC_URL:-}"
DATA_PATH="${DATA_PATH:-/}"
ALERT_AT_PCT="${ALERT_AT_PCT:-80}"
PRUNE_AT_PCT="${PRUNE_AT_PCT:-85}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-/opt/sorento-crm2/backups/pre-migrate}"
SNAPSHOT_KEEP="${SNAPSHOT_KEEP:-2}"
ETCD_MEMBERS="${ETCD_MEMBERS:-3}"
ETCD_ONLY="${ETCD_ONLY:-0}"
MAX_LAG_BYTES="${MAX_LAG_BYTES:-8388608}"          # half of maximum_lag_on_failover
MAX_ARCHIVE_AGE_S="${MAX_ARCHIVE_AGE_S:-600}"
MAX_WAL_BYTES="${MAX_WAL_BYTES:-10737418240}"      # 10 GB
MAX_BACKUP_AGE_S="${MAX_BACKUP_AGE_S:-93600}"      # 26 h
PATRONI_URL="${PATRONI_URL:-http://127.0.0.1:8008/primary}"
PATRONI_CLUSTER_URL="${PATRONI_CLUSTER_URL:-http://127.0.0.1:8008/cluster}"
PROJECT_DIR="${PROJECT_DIR:-/opt/sorento-crm2}"
ETCD_SERVICE="${ETCD_SERVICE:-etcd}"
COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.yml -f compose.ha.yml}"
DB_SERVICE="${DB_SERVICE:-db}"

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

# 2. etcd quorum members (etcd runs in a container; ETCDCTL_USER comes from etcd.env).
# shellcheck disable=SC2086
healthy=$(docker compose $COMPOSE_FILES exec -T "$ETCD_SERVICE" sh -c 'etcdctl endpoint health --cluster' 2>&1 | grep -c "is healthy" || true)
if [ "$healthy" -lt "$ETCD_MEMBERS" ]; then note "etcd ${healthy}/${ETCD_MEMBERS} members healthy"; fi

# 3. Exactly one leader in the Patroni cluster (both nodes as replicas would otherwise look fine).
if [ "$ETCD_ONLY" != "1" ]; then
  leaders=$(curl -s -m 3 "$PATRONI_CLUSTER_URL" 2>/dev/null | python3 -c 'import json,sys
try:
    m = json.load(sys.stdin).get("members", [])
    print(sum(1 for x in m if x.get("role") in ("leader", "standby_leader")))
except Exception:
    print(-1)' 2>/dev/null)
  if [ "${leaders:--1}" = "-1" ]; then note "patroni cluster state unreadable"
  elif [ "$leaders" != "1" ]; then note "patroni cluster has ${leaders} leaders"; fi
fi

# 4. Leader-only Postgres checks.
if [ "$ETCD_ONLY" != "1" ]; then
  code=$(curl -s -o /dev/null -m 3 -w '%{http_code}' "$PATRONI_URL" 2>/dev/null) || code=000
  if [ "$code" = "200" ]; then
    replicas=$(sql "SELECT count(*) FROM pg_stat_replication WHERE state = 'streaming'")
    if [ "${replicas:-0}" -lt 1 ]; then note "no replica streaming"; fi
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
  elif [ "$code" = "000" ]; then
    note "patroni not answering"
  fi
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
