#!/usr/bin/env bash
# Re-record one training video:  scripts/training-videos/record.sh <video-id> [--no-voice]
#
# Seed the fake data first (separate step, idempotent), from sorento_crm_backend/:
#   SORENTO_ENV_FILE=.env.ci-tests no_proxy='*' venv/bin/python ../scripts/training-videos/seed_fake.py --part p1
#   (part p2 also needs TV_API_URL=http://127.0.0.1:<backend port>/api/v1)
#
# Env: TV_BASE_URL (frontend, default http://localhost:3000), NODE_PATH (default the repo's
# sorento_crm_frontend/node_modules, for playwright). Output lands in scripts/training-videos/out/.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
[ $# -ge 1 ] || { echo "usage: $0 <video-id> [--no-voice]" >&2; exit 2; }
export TV_BASE_URL="${TV_BASE_URL:-http://localhost:3000}"
export NODE_PATH="${NODE_PATH:-$here/../../sorento_crm_frontend/node_modules}"
exec node "$here/lib/recorder.mjs" "$@"
