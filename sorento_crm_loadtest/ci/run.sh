#!/usr/bin/env bash
# Usage: ./ci/run.sh <profile> <scenario>
#   profile  = smoke | load | stress | spike | soak
#   scenario = path under scenarios/, e.g. n8n/stock_inquiry_revise
#
# Env (loaded from .env automatically):
#   TARGET=local|staging|prod
#   K6_OUT=...   (optional, e.g. influxdb=http://localhost:8086/k6)

set -euo pipefail

PROFILE="${1:-${PROFILE:-smoke}}"
SCENARIO="${2:-}"

if [[ -z "$SCENARIO" ]]; then
  echo "usage: $0 <profile> <scenario>" >&2
  echo "  e.g. $0 smoke n8n/stock_inquiry_revise" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="${ROOT}/scenarios/${SCENARIO}.js"

if [[ ! -f "$SCRIPT" ]]; then
  echo "scenario not found: $SCRIPT" >&2
  exit 1
fi

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

TARGET="${TARGET:-local}"
TS=$(date -u +"%Y%m%dT%H%M%SZ")
SAFE_NAME=$(echo "$SCENARIO" | tr '/' '_')
SUMMARY="${ROOT}/results/${SAFE_NAME}-${PROFILE}-${TARGET}-${TS}.json"

mkdir -p "${ROOT}/results"

K6_ARGS=(
  run
  -e "PROFILE=${PROFILE}"
  -e "TARGET=${TARGET}"
  --summary-export "${SUMMARY}"
)

if [[ -n "${K6_OUT:-}" ]]; then
  K6_ARGS+=( --out "${K6_OUT}" )
fi

echo "[run.sh] profile=${PROFILE} scenario=${SCENARIO} target=${TARGET}"
echo "[run.sh] summary -> ${SUMMARY}"

exec k6 "${K6_ARGS[@]}" "$SCRIPT"
