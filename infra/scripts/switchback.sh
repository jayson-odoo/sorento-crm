#!/usr/bin/env bash
# Automatic switchback to KL (HA-TIER1-N8N-BOX, owner ruling O3 (a), 27 Oct).
# Plan: documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md section 2 "Failback".
#
# Cron every 5 minutes on the KL node. After a failover to India, KL rejoins as a replica on its
# own; this moves the primary back to KL with a planned `patronictl switchover` (a 5-15 s write
# pause, no data loss) only when ALL hold:
#   - KL is a streaming replica at most MAX_LAG_MB behind, and has been continuously so for
#     HEALTHY_HOURS (Patroni's "Lag in MB" is up to 10 s stale, so a write burst reads a few MB;
#     Patroni refuses a lagging candidate at switchover time anyway);
#   - the leader is another member and the cluster is not paused (maintenance mode);
#   - the local time in SWITCH_TZ is inside the window starting SWITCH_AT (default 04:00 MYT,
#     clear of the 03:00 nightly pg_dump in documentation/runbooks/backups.md).
# Any unhealthy reading resets the clock (marker file). Never acts while KL already leads.
#
# Env (optional): HOME_MEMBER (kl), HEALTHY_HOURS (24), MAX_LAG_MB (16), SWITCH_AT (04:00),
# WINDOW_MIN (10), SWITCH_TZ (Asia/Kuala_Lumpur), STATE_DIR, PROJECT_DIR, COMPOSE_FILES,
# DB_SERVICE, PATRONI_CLUSTER_URL, NOW (tests: epoch).
set -uo pipefail

HOME_MEMBER="${HOME_MEMBER:-kl}"
HEALTHY_HOURS="${HEALTHY_HOURS:-24}"
MAX_LAG_MB="${MAX_LAG_MB:-16}"
SWITCH_AT="${SWITCH_AT:-04:00}"
WINDOW_MIN="${WINDOW_MIN:-10}"
SWITCH_TZ="${SWITCH_TZ:-Asia/Kuala_Lumpur}"
STATE_DIR="${STATE_DIR:-/var/lib/sorento-ha}"
PROJECT_DIR="${PROJECT_DIR:-/opt/sorento-crm2}"
PATRONI_CLUSTER_URL="${PATRONI_CLUSTER_URL:-http://127.0.0.1:8008/cluster}"
COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.yml -f compose.ha.yml}"
DB_SERVICE="${DB_SERVICE:-db}"
NOW="${NOW:-$(date +%s)}"
MARKER="$STATE_DIR/${HOME_MEMBER}-healthy-since"

log() { echo "$(date -u -d "@$NOW" +%Y-%m-%dT%H:%M:%SZ) switchback: $*"; }

patronictl() {
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES exec -T "$DB_SERVICE" /opt/patroni/bin/patronictl -c /etc/patroni/patroni.yml "$@"
}

# Cron starts in $HOME; the compose files are relative.
cd "$PROJECT_DIR" || { echo "switchback: cannot cd to $PROJECT_DIR" >&2; exit 2; }
mkdir -p "$STATE_DIR" || { log "cannot create $STATE_DIR"; exit 2; }
members=$(patronictl list -f json 2>/dev/null) || { log "patronictl list failed"; rm -f "$MARKER"; exit 1; }

# "<home role>|<home state>|<home lag MB>|<leader name>"
summary=$(printf '%s' "$members" | python3 -c '
import json, sys
home = sys.argv[1]
rows = json.load(sys.stdin)
me = next((r for r in rows if r.get("Member") == home), {})
leader = next((r.get("Member") for r in rows if r.get("Role") in ("Leader", "Standby Leader")), "")
lag = me.get("Lag in MB", "")
print("|".join([str(me.get("Role", "")), str(me.get("State", "")), str(lag), leader]))
' "$HOME_MEMBER" 2>/dev/null) || { log "cannot parse patronictl output"; rm -f "$MARKER"; exit 1; }
IFS='|' read -r role state lag leader <<<"$summary"

if [ "$role" = "Leader" ]; then
  rm -f "$MARKER"
  exit 0
fi
case "$role" in Replica|"Sync Standby"|"Quorum Standby") role_ok=1 ;; *) role_ok=0 ;; esac
case "$lag" in ''|*[!0-9]*) lag_ok=0 ;; *) [ "$lag" -le "$MAX_LAG_MB" ] && lag_ok=1 || lag_ok=0 ;; esac
if [ "$role_ok" != 1 ] || [ "$state" != "streaming" ] || [ "$lag_ok" != 1 ]; then
  log "$HOME_MEMBER not a caught-up streaming replica (role=$role state=$state lag=$lag); clock reset"
  rm -f "$MARKER"
  exit 0
fi
since=$(cat "$MARKER" 2>/dev/null || true)
case "$since" in ''|*[!0-9]*) echo "$NOW" > "$MARKER" || { log "cannot write $MARKER"; exit 2; }; since=$NOW ;; esac
healthy_s=$((NOW - since))
if [ "$healthy_s" -lt $((HEALTHY_HOURS * 3600)) ]; then exit 0; fi

# Minutes since local midnight, now and at SWITCH_AT.
now_min=$(TZ="$SWITCH_TZ" date -d "@$NOW" +%H:%M | awk -F: '{ print $1 * 60 + $2 }')
at_min=$(echo "$SWITCH_AT" | awk -F: '{ print $1 * 60 + $2 }')
if [ "$now_min" -lt "$at_min" ] || [ "$now_min" -ge $((at_min + WINDOW_MIN)) ]; then exit 0; fi
if [ -z "$leader" ] || [ "$leader" = "$HOME_MEMBER" ]; then
  log "no switchover: leader='$leader'"
  exit 0
fi
paused=$(curl -s -m 3 "$PATRONI_CLUSTER_URL" 2>/dev/null | python3 -c 'import json,sys
try: print("1" if json.load(sys.stdin).get("pause") else "0")
except Exception: print("?")' 2>/dev/null)
if [ "$paused" != "0" ]; then
  log "no switchover: cluster paused or state unreadable (pause=$paused)"
  exit 0
fi

log "$HOME_MEMBER healthy for $((healthy_s / 3600)) h; switching over from $leader"
if patronictl switchover --leader "$leader" --candidate "$HOME_MEMBER" --force; then
  rm -f "$MARKER"
  exit 0
fi
log "switchover failed; will retry inside the window"
exit 1
