#!/bin/sh
# chatbot-stack-check.sh - read-only diagnostic for a chatbot lane stack.
#
# Prints, one line each: which worktree/commit the backend and MCP processes bound to
# these ports are actually running from, the backend's own /health sha (when it carries
# one), the clone DB's alembic head and which chatbot_semantic_parser prompt version
# currently carries the "production" label, and the machine's load/disk headroom.
#
# Never restarts anything and never writes. Exits non-zero (with a clear line naming
# why) when the MCP process's worktree does not match the backend's, or when the 1-minute
# load average is above 20 - both conditions that make any turn measured against this
# stack unreliable regardless of what the code actually does.
#
# Usage: scripts/chatbot-stack-check.sh [backend_port] [frontend_port]
#   defaults: backend_port=8081 frontend_port=3081

set -eu

BE_PORT="${1:-8081}"
FE_PORT="${2:-3081}"
MCP_PORT="8765"

FAIL=0

# The worktree root a given directory belongs to (works for the primary checkout and any
# linked worktree alike - `git rev-parse --show-toplevel` follows the `.git` file a linked
# worktree carries, not just a `.git` directory).
worktree_root() {
  dir="$1"
  if [ -z "$dir" ] || [ ! -d "$dir" ]; then
    printf ''
    return
  fi
  (cd "$dir" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null) || printf ''
}

pid_on_port() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | head -1
}

cwd_of_pid() {
  pid="$1"
  [ -z "$pid" ] && return
  lsof -p "$pid" 2>/dev/null | awk '$4 == "cwd" { print $NF; exit }'
}

echo "=== chatbot-stack-check: backend :$BE_PORT  frontend :$FE_PORT  mcp :$MCP_PORT ==="
echo

# --- this script's own worktree + commit --------------------------------------------- #
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SELF_WT=$(worktree_root "$SCRIPT_DIR")
echo "this script's worktree: ${SELF_WT:-<not a git checkout>}"
if [ -n "$SELF_WT" ]; then
  echo "this script's HEAD:     $(cd "$SELF_WT" && git rev-parse --short HEAD 2>/dev/null || echo '<unknown>')"
fi
echo

# --- backend process ------------------------------------------------------------------ #
BE_PID=$(pid_on_port "$BE_PORT")
if [ -z "$BE_PID" ]; then
  echo "backend :$BE_PORT - no process listening"
  BE_CWD=""
  BE_WT=""
else
  BE_CWD=$(cwd_of_pid "$BE_PID")
  BE_WT=$(worktree_root "$BE_CWD")
  echo "backend :$BE_PORT - pid $BE_PID, cwd ${BE_CWD:-<unknown>}"
  echo "backend worktree: ${BE_WT:-<unknown - not inside a git checkout>}"
  if [ -n "$BE_WT" ]; then
    echo "backend worktree HEAD: $(cd "$BE_WT" && git rev-parse --short HEAD 2>/dev/null || echo '<unknown>')"
  fi
fi
echo

# --- backend's own /health sha --------------------------------------------------------- #
HEALTH_JSON=$(curl -s -m 5 "http://localhost:$BE_PORT/health" 2>/dev/null || printf '')
if [ -z "$HEALTH_JSON" ]; then
  echo "GET /health - no response (backend down, or not listening on :$BE_PORT)"
else
  SHA=$(printf '%s' "$HEALTH_JSON" | python3 -c '
import json, sys
try:
    body = json.load(sys.stdin)
except Exception:
    body = {}
sha = body.get("git_sha") if isinstance(body, dict) else None
print(sha or "")
' 2>/dev/null || printf '')
  if [ -n "$SHA" ]; then
    echo "GET /health git_sha: $SHA"
  else
    echo "health has no sha"
  fi
fi
echo

# --- MCP process ------------------------------------------------------------------------ #
MCP_PID=$(pid_on_port "$MCP_PORT")
if [ -z "$MCP_PID" ]; then
  echo "mcp :$MCP_PORT - no process listening"
  MCP_CWD=""
  MCP_WT=""
else
  MCP_CWD=$(cwd_of_pid "$MCP_PID")
  MCP_WT=$(worktree_root "$MCP_CWD")
  echo "mcp :$MCP_PORT - pid $MCP_PID, cwd ${MCP_CWD:-<unknown>}"
  echo "mcp worktree: ${MCP_WT:-<unknown - not inside a git checkout>}"

  MCP_CMD=$(ps -p "$MCP_PID" -o command= 2>/dev/null || printf '')
  MCP_PY=$(printf '%s' "$MCP_CMD" | awk '{print $1}')
  if [ -n "$MCP_PY" ] && [ -x "$MCP_PY" ]; then
    MCP_FILE=$("$MCP_PY" -c 'import sorento_crm_mcp; print(sorento_crm_mcp.__file__)' 2>/dev/null || printf '')
    if [ -n "$MCP_FILE" ]; then
      echo "sorento_crm_mcp.__file__ (via $MCP_PY's PYTHONPATH): $MCP_FILE"
    else
      echo "sorento_crm_mcp.__file__: could not import under $MCP_PY"
    fi
  else
    echo "sorento_crm_mcp.__file__: could not read the mcp process's interpreter from its command line"
  fi
fi
echo

# --- MCP cwd must be under the SAME worktree as the backend ---------------------------- #
if [ -n "$BE_WT" ] && [ -n "$MCP_WT" ] && [ "$BE_WT" != "$MCP_WT" ]; then
  echo "MISMATCH: mcp worktree ($MCP_WT) is not the backend's worktree ($BE_WT)"
  echo "          the MCP catalog this backend calls into may be stale or belong to another lane."
  FAIL=1
fi
echo

# --- clone DB: alembic head + which parser prompt version carries "production" --------- #
DB_URL=""
if [ -n "$BE_WT" ] && [ -f "$BE_WT/sorento_crm_backend/.env" ]; then
  DB_URL=$(grep -E '^DATABASE_URL=' "$BE_WT/sorento_crm_backend/.env" | head -1 | cut -d= -f2-)
fi
if [ -z "$DB_URL" ]; then
  echo "database: could not resolve DATABASE_URL from ${BE_WT:-<unknown backend worktree>}/sorento_crm_backend/.env"
else
  DB_NAME=$(printf '%s' "$DB_URL" | sed -E 's#.*/([^/?]+)(\?.*)?$#\1#')
  echo "database: $DB_NAME (from $BE_WT/sorento_crm_backend/.env)"
  if command -v psql >/dev/null 2>&1; then
    ALEMBIC=$(psql "$DB_URL" -tAc "SELECT version_num FROM alembic_version" 2>/dev/null | tr -d '[:space:]')
    echo "alembic_version: ${ALEMBIC:-<not found - table missing or unreachable>}"

    PARSER_PROD=$(psql "$DB_URL" -tAc "
      SELECT v.version
      FROM ai_prompt_versions v
      JOIN ai_prompt_labels l ON l.version_id = v.id
      WHERE v.name = 'chatbot_semantic_parser'
        AND l.name = 'chatbot_semantic_parser'
        AND l.label = 'production'
      ORDER BY v.version DESC
      LIMIT 1
    " 2>/dev/null | tr -d '[:space:]')
    echo "chatbot_semantic_parser prompt version carrying the 'production' label: ${PARSER_PROD:-<none found>}"
  else
    echo "alembic_version / prompt version: psql not on PATH, skipped"
  fi
fi
echo

# --- load / disk ------------------------------------------------------------------------ #
UPTIME_LINE=$(uptime)
echo "uptime: $UPTIME_LINE"
LOAD1=$(printf '%s' "$UPTIME_LINE" | sed -E 's/.*load average[s]?: *([0-9.]+).*/\1/')
if printf '%s' "$LOAD1" | grep -Eq '^[0-9.]+$'; then
  OVER=$(awk -v l="$LOAD1" 'BEGIN { print (l > 20) ? 1 : 0 }')
  if [ "$OVER" = "1" ]; then
    echo "LOAD TOO HIGH: 1-minute load average $LOAD1 is above 20 - readings from this stack are unreliable."
    FAIL=1
  fi
else
  echo "load: could not parse a 1-minute figure out of uptime's own line"
fi

echo "df -h /: $(df -h / 2>/dev/null | tail -1)"
echo

if [ "$FAIL" -ne 0 ]; then
  echo "=== chatbot-stack-check: FAILED - see MISMATCH/LOAD line(s) above ==="
  exit 1
fi
echo "=== chatbot-stack-check: OK ==="
exit 0
