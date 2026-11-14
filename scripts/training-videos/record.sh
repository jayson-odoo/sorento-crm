#!/usr/bin/env bash
# Re-record one training video, from a clean seed:
#   TV_BASE_URL=http://localhost:<fe port> [TV_API_URL=http://127.0.0.1:<be port>/api/v1] \
#     scripts/training-videos/record.sh <video-id> [--no-voice]
#
# 1. Seeds the fake data part the id's prefix names (p1-*, p2-* or p3-*) with seed_fake.py, which
#    also resets whatever an earlier take left behind. Parts p2 and p3 drive the backend, so they
#    need TV_API_URL. The seeder reads SORENTO_ENV_FILE (default .env.ci-tests) from sorento_crm_backend/
#    and refuses any database but the local sorento_ci_tv.
# 2. Records with lib/recorder.mjs. TV_BASE_URL has no default (port 3000 can be another lane's
#    frontend); NODE_PATH defaults to the repo's sorento_crm_frontend/node_modules (playwright).
# Output lands in scripts/training-videos/out/.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
[ $# -ge 1 ] || { echo "usage: $0 <video-id> [--no-voice]" >&2; exit 2; }
: "${TV_BASE_URL:?set TV_BASE_URL to the frontend of this lane, e.g. http://localhost:3277}"
part="${1%%-*}"
case "$part" in
  p1) ;;
  p2|p3) : "${TV_API_URL:?part $part needs TV_API_URL, the backend /api/v1 base of this lane}" ;;
  *) echo "video id must start with p1-, p2- or p3-: $1" >&2; exit 2 ;;
esac
(cd "$here/../../sorento_crm_backend" && SORENTO_ENV_FILE="${SORENTO_ENV_FILE:-.env.ci-tests}" no_proxy='*' \
  venv/bin/python ../scripts/training-videos/seed_fake.py --part "$part")
export TV_BASE_URL
export NODE_PATH="${NODE_PATH:-$here/../../sorento_crm_frontend/node_modules}"
exec node "$here/lib/recorder.mjs" "$@"
