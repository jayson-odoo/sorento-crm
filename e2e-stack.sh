#!/bin/zsh
# Launch / stop / status for the disposable SCM e2e integration stack in this worktree.
# Processes are detached (nohup + disown; macOS has no setsid) so they outlive any
# agent shell. Logs and pidfiles live under .e2e-stack/ (gitignored via .git/info/exclude).
#   ./e2e-stack.sh start | stop | status
set -u
ROOT="${0:A:h}"
RUN="$ROOT/.e2e-stack"
mkdir -p "$RUN"
BE_PORT=8030
FE_PORT=3050

start_one() {
  local name=$1 dir=$2; shift 2
  if [[ -f "$RUN/$name.pid" ]] && kill -0 "$(cat "$RUN/$name.pid")" 2>/dev/null; then
    echo "$name already running pid $(cat "$RUN/$name.pid")"; return
  fi
  cd "$dir" || exit 1
  nohup "$@" > "$RUN/$name.log" 2>&1 < /dev/null &
  echo $! > "$RUN/$name.pid"
  disown
  echo "$name started pid $(cat "$RUN/$name.pid")"
}

case "${1:-status}" in
  start)
    ENABLE_SCHEDULER=false start_one backend "$ROOT/sorento_crm_backend" \
      venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $BE_PORT
    PGGSSENCMODE=disable OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES start_one worker "$ROOT/sorento_crm_backend" \
      venv/bin/python worker.py
    start_one frontend "$ROOT/sorento_crm_frontend" \
      npm run dev -- --port $FE_PORT
    ;;
  stop)
    for n in frontend worker backend; do
      [[ -f "$RUN/$n.pid" ]] && { kill "$(cat "$RUN/$n.pid")" 2>/dev/null; rm -f "$RUN/$n.pid"; echo "$n stopped"; }
    done
    ;;
  status)
    for n in backend worker frontend; do
      if [[ -f "$RUN/$n.pid" ]] && kill -0 "$(cat "$RUN/$n.pid")" 2>/dev/null; then echo "$n up pid $(cat "$RUN/$n.pid")"; else echo "$n DOWN"; fi
    done
    curl -s -o /dev/null -w "backend /health %{http_code}\n" --max-time 5 http://localhost:$BE_PORT/health
    curl -s -o /dev/null -w "frontend /signin %{http_code}\n" --max-time 60 http://localhost:$FE_PORT/signin
    ;;
esac
