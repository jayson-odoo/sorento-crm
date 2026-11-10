#!/usr/bin/env bash
# Two-node release (HA-CF-FAILOVER). Runs on the CI runner, not on a server.
# Plan: documentation/plans/infra/PLAN-ha-cf-failover-04nov.md section 2 row 1.
#
# One release, one image tag, both nodes, PRIMARY FIRST:
#   1. copy scripts/blue_green_deploy.sh to every host and ask each its role (--role);
#   2. refuse unless exactly one host is primary (nothing is deployed otherwise);
#   3. deploy the primary (migrations + snapshot happen there, as today);
#   4. deploy every standby (its blue_green_deploy.sh runs in standby mode: SKIP_MIGRATIONS=1,
#      waits for the replicated schema, never touches workers);
#   5. ask the roles again: a failover during the release fails it (re-run on the new primary).
# A standby that cannot be reached is skipped and the release FAILS at the end, after the
# primary is done, so users get the new code and the owner gets a red run to look at.
#
# Env: HA_HOSTS (space-separated), SSH_USER, SSH_KEY_FILE, KNOWN_HOSTS_FILE (both hosts' keys:
#      a host whose key is not in it is refused, never trusted on first use), IMAGE_TAG (40 hex),
#      [REMOTE_DIR=/opt/sorento-crm2] [SSH=ssh] [SCP=scp]
set -uo pipefail

: "${HA_HOSTS:?space-separated hosts}" "${SSH_USER:?}" "${SSH_KEY_FILE:?}" "${IMAGE_TAG:?}"
: "${KNOWN_HOSTS_FILE:?the public keys of both hosts, secret SSH_KNOWN_HOSTS}"
[ -s "$KNOWN_HOSTS_FILE" ] || { echo "ERROR: KNOWN_HOSTS_FILE is empty; set the SSH_KNOWN_HOSTS secret. Nothing was deployed."; exit 1; }
[[ "$IMAGE_TAG" =~ ^[0-9a-f]{40}$ ]] || { echo "ERROR: IMAGE_TAG must be a 40 hex git SHA"; exit 1; }
REMOTE_DIR="${REMOTE_DIR:-/opt/sorento-crm2}"
SSH="${SSH:-ssh}"
SCP="${SCP:-scp}"
SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$KNOWN_HOSTS_FILE"
SCRIPT="$(cd "$(dirname "$0")" && pwd)/blue_green_deploy.sh"

# shellcheck disable=SC2086
remote() { local h=$1; shift; $SSH $SSH_OPTS -i "$SSH_KEY_FILE" "$SSH_USER@$h" "$@" </dev/null; }

roles() {
  local h r
  for h in $HA_HOSTS; do
    r=$(remote "$h" "cd $REMOTE_DIR && ./scripts/blue_green_deploy.sh --role" 2>/dev/null | tail -1) || r=unreachable
    case "$r" in primary|standby|single|unknown) ;; *) r=unreachable ;; esac
    echo "$h $r"
  done
}

echo "==> Copying the deploy script to every host"
for h in $HA_HOSTS; do
  # shellcheck disable=SC2086
  $SCP $SSH_OPTS -i "$SSH_KEY_FILE" "$SCRIPT" "$SSH_USER@$h:$REMOTE_DIR/scripts/blue_green_deploy.sh" \
    || echo "    $h: copy failed"
  remote "$h" "chmod +x $REMOTE_DIR/scripts/blue_green_deploy.sh" >/dev/null 2>&1 || true
done

echo "==> Roles"
before=$(roles)
printf '    %s\n' "${before//$'\n'/$'\n'    }"
primaries=$(awk '$2 == "primary" { print $1 }' <<< "$before")
n_primary=$(grep -c . <<< "$primaries" || true)
if [ "$n_primary" != 1 ]; then
  echo "ERROR: expected exactly one primary, found ${n_primary}. Nothing was deployed."
  exit 1
fi
if awk '$2 == "single" || $2 == "unknown" { bad = 1 } END { exit !bad }' <<< "$before"; then
  echo "ERROR: a host is not an HA node or its role is unknown (see above). Nothing was deployed."
  exit 1
fi
primary=$primaries

echo "==> Deploying the primary ($primary)"
if ! remote "$primary" "cd $REMOTE_DIR && IMAGE_TAG=$IMAGE_TAG ./scripts/blue_green_deploy.sh"; then
  echo "ERROR: the primary's deploy failed; standbys were not touched."
  exit 1
fi

failed=0
while read -r h r; do
  [ "$h" = "$primary" ] && continue
  if [ "$r" != standby ]; then
    echo "ERROR: $h was $r, not deployed"
    failed=1
    continue
  fi
  echo "==> Deploying the standby ($h)"
  if ! remote "$h" "cd $REMOTE_DIR && IMAGE_TAG=$IMAGE_TAG ./scripts/blue_green_deploy.sh"; then
    echo "ERROR: the standby's deploy failed on $h"
    failed=1
  fi
done <<< "$before"

echo "==> Roles after the release"
after=$(roles)
printf '    %s\n' "${after//$'\n'/$'\n'    }"
if [ "$(awk '$2 == "primary" { print $1 }' <<< "$after")" != "$primary" ]; then
  echo "ERROR: the primary changed during the release (a failover); re-run the release."
  exit 1
fi
[ "$failed" = 0 ] || exit 1
echo "==> Release complete on every node"
