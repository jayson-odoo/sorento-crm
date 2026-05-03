#!/usr/bin/env bash
# Capture host/container metrics during a stress test.
#
# Usage:
#   ./ci/capture-host.sh <duration-seconds> <output-prefix> [container1 container2 ...]
#
# Examples:
#   ./ci/capture-host.sh 600 results/run-2026-05-02-stress sorento_crm_backend sorento_crm_db
#   ./ci/capture-host.sh 900 results/listings-stress backend db mcp
#
# Run this in a second terminal alongside `./ci/run.sh stress ...`.
# Records: docker stats CSV, vmstat, iostat (if available).

set -euo pipefail

DURATION="${1:-300}"
PREFIX="${2:-host-capture-$(date -u +%Y%m%dT%H%M%SZ)}"
shift 2 || true
CONTAINERS=("$@")

if [[ ${#CONTAINERS[@]} -eq 0 ]]; then
  CONTAINERS=( $(docker ps --format '{{.Names}}') )
fi

mkdir -p "$(dirname "$PREFIX")"

echo "[capture] duration=${DURATION}s containers=${CONTAINERS[*]} prefix=${PREFIX}"

# 1. docker stats — CPU%, mem, net, blockIO, pids
(
  echo "ts,name,cpu_pct,mem_usage,mem_pct,net_io,block_io,pids"
  end=$(( $(date +%s) + DURATION ))
  while [[ $(date +%s) -lt $end ]]; do
    docker stats --no-stream --format \
      '{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}},{{.NetIO}},{{.BlockIO}},{{.PIDs}}' \
      "${CONTAINERS[@]}" 2>/dev/null \
      | awk -v ts="$(date -u +%FT%TZ)" -F',' '{print ts","$0}'
    sleep 2
  done
) > "${PREFIX}-docker-stats.csv" &
PID_DOCKER=$!

# 2. vmstat — host CPU, memory, IO, context switches (1s sample)
(vmstat 1 "$DURATION") > "${PREFIX}-vmstat.txt" 2>&1 &
PID_VMSTAT=$!

# 3. iostat if present
if command -v iostat >/dev/null 2>&1; then
  (iostat -xz 2 $((DURATION/2))) > "${PREFIX}-iostat.txt" 2>&1 &
  PID_IOSTAT=$!
fi

trap 'kill "$PID_DOCKER" "$PID_VMSTAT" ${PID_IOSTAT:-} 2>/dev/null || true' EXIT

wait $PID_DOCKER $PID_VMSTAT ${PID_IOSTAT:-} 2>/dev/null || true

echo "[capture] done. files: ${PREFIX}-*"
