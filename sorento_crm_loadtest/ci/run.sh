#!/usr/bin/env bash
# Usage: ./ci/run.sh <profile> <scenario>
#   profile  = smoke | load | stress | spike | soak
#   scenario = path under scenarios/, e.g. n8n/stock_inquiry_revise
#
# Env (loaded from .env automatically):
#   TARGET=local|staging|prod
#   K6_OUT=...   (optional, e.g. influxdb=http://localhost:8086/k6)

set -euo pipefail

CLI_PROFILE="${1:-}"
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

# CLI arg always wins over .env PROFILE
PROFILE="${CLI_PROFILE:-${PROFILE:-smoke}}"
TARGET="${TARGET:-local}"
TS=$(date -u +"%Y%m%dT%H%M%SZ")
SAFE_NAME=$(echo "$SCENARIO" | tr '/' '_')
SUMMARY="${ROOT}/results/${SAFE_NAME}-${PROFILE}-${TARGET}-${TS}.json"
K6_RUN_ID="${SAFE_NAME}-${PROFILE}-${TARGET}-${TS}"
export K6_RUN_ID

mkdir -p "${ROOT}/results"

K6_ARGS=(
  run
  -e "PROFILE=${PROFILE}"
  -e "TARGET=${TARGET}"
  --summary-export "${SUMMARY}"
)

# Forward all relevant env vars to k6 (only if set, so we don't override defaults).
for var in \
  NEXTAUTH_SECRET JWT_TTL_SECONDS \
  LOADTEST_USER_EMAIL LOADTEST_USER_PASSWORD \
  LOADTEST_CONTACT_ID LOADTEST_SPACE_ID \
  EXTERNAL_API_KEY \
  BE_LOCAL_URL FE_LOCAL_URL BE_STAGING_URL FE_STAGING_URL BE_PROD_URL FE_PROD_URL \
  N8N_LOADTEST_STOCK_INQUIRY_REVISE_URL N8N_LOADTEST_ATTACHMENT_URL N8N_LOADTEST_CRM_CHAT_OUTBOUND_URL \
  N8N_ALLOW_PROD_URL \
  FE_NEXTAUTH_COOKIE \
  K6_PEAK_RPS K6_STAGE_MIN K6_HOLD_MIN K6_MAX_VUS SOAK_DURATION K6_RUN_ID \
  AI_VUS AI_DURATION ATTACHMENT_SIZE BROWSER_VUS BROWSER_ITERATIONS \
  PORTAL_CONTACT_ID PORTAL_SPACE_ID
do
  val="${!var-}"
  if [[ -n "$val" ]]; then
    K6_ARGS+=( -e "${var}=${val}" )
  fi
done

if [[ -n "${K6_OUT:-}" ]]; then
  K6_ARGS+=( --out "${K6_OUT}" )
fi

echo "[run.sh] profile=${PROFILE} scenario=${SCENARIO} target=${TARGET}"
echo "[run.sh] summary -> ${SUMMARY}"

exec k6 "${K6_ARGS[@]}" "$SCRIPT"
