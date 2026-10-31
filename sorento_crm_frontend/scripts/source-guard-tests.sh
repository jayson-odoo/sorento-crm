#!/usr/bin/env bash
# Prints, NUL-separated, every vitest file that reads the source tree from disk
# (readFileSync / readdirSync / existsSync / a glob) instead of importing it.
#
# Why: `vitest run --changed <base>` picks tests through the module graph, so a
# test that scans files with fs never looks related to the file it scans. The
# PR gate missed two such guards on #2051 and release 14 went red on them.
# Selecting by the fs call itself needs no list to keep up to date: a new guard
# is picked up the day it lands.
#
# Usage (from sorento_crm_frontend/):
#   scripts/source-guard-tests.sh | xargs -0 npx vitest run
set -euo pipefail
cd "$(dirname "$0")/.."
grep -rlZE \
  --include='*.test.ts' --include='*.test.tsx' \
  --exclude-dir=node_modules --exclude-dir=.next --exclude-dir=e2e \
  '\b(readFileSync|readdirSync|readFile|opendirSync|existsSync|globSync)\b|import\.meta\.glob' \
  .
