#!/usr/bin/env bash
# Automatic switchback to KL (HA-TIER1-N8N-BOX, owner ruling O3 (a), 27 Oct).
# Plan: documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md section 2 "Failback".
#
# Cron every 5 minutes on the KL node. After a failover to India, KL rejoins as a replica on its
# own; this moves the primary back to KL with a planned `patronictl switchover` (a 5-15 s write
# pause, no data loss) only when ALL hold:
#   - KL is a replica, streaming, 0 MB behind, and has been continuously so for HEALTHY_HOURS;
#   - the leader is another member (Patroni itself refuses a second scheduled switchover);
#   - the local time in SWITCH_TZ is inside the window starting SWITCH_AT (default 03:00 MYT).
# Any unhealthy reading resets the clock (marker file). Never acts while KL already leads.
#
# Env (optional): HOME_MEMBER (kl), HEALTHY_HOURS (24), SWITCH_AT (03:00), WINDOW_MIN (10),
# SWITCH_TZ (Asia/Kuala_Lumpur), STATE_DIR, COMPOSE_FILES, DB_SERVICE, NOW (tests: epoch).
set -uo pipefail

HOME_MEMBER="${HOME_MEMBER:-kl}"
HEALTHY_HOURS="${HEALTHY_HOURS:-24}"
SWITCH_AT="${SWITCH_AT:-03:00}"
WINDOW_MIN="${WINDOW_MIN:-10}"
SWITCH_TZ="${SWITCH_TZ:-Asia/Kuala_Lumpur}"
STATE_DIR="${STATE_DIR:-/var/lib/sorento-ha}"
COMPOSE_FILES="${COMPOSE_FILES:--f docker-compose.yml -f compose.ha.yml}"
DB_SERVICE="${DB_SERVICE:-db}"
NOW="${NOW:-$(date +%s)}"
MARKER="$STATE_DIR/${HOME_MEMBER}-healthy-since"

log() { echo "$(date -u -d "@$NOW" +%Y-%m-%dT%H:%M:%SZ) switchback: $*"; }

patronictl() {
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES exec -T "$DB_SERVICE" /opt/patroni/bin/patronictl -c /etc/patroni/patroni.yml "$@"
}

mkdir -p "$STATE_DIR"
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
if [ "$role" != "Replica" ] && [ "$role" != "Sync Standby" ] || [ "$state" != "streaming" ] || [ "$lag" != "0" ]; then
  log "$HOME_MEMBER not a caught-up streaming replica (role=$role state=$state lag=$lag); clock reset"
  rm -f "$MARKER"
  exit 0
fi
[ -s "$MARKER" ] || echo "$NOW" > "$MARKER"
since=$(cat "$MARKER")
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

log "$HOME_MEMBER healthy for $((healthy_s / 3600)) h; switching over from $leader"
if patronictl switchover --leader "$leader" --candidate "$HOME_MEMBER" --force; then
  rm -f "$MARKER"
  exit 0
fi
log "switchover failed; will retry inside the window"
exit 1
