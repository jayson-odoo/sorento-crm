"""Gunicorn config for the FastAPI backend.

Why preload_app: measured on prod (srv1250216, 10 Sep 2026) at 4.7 GB for
4 UvicornWorker gunicorn workers with no --preload, roughly 1.2 GB of PRIVATE
memory each - every worker independently imports the full app (SQLAlchemy
models, the embedding pipeline, Playwright/WeasyPrint-adjacent imports) before
it can serve anything. `preload_app = True` loads the app ONCE in the
gunicorn master before forking, so the workers share that memory
copy-on-write instead of each holding its own private copy. A blue/green
deploy briefly runs two colours side by side (backend_blue + backend_green,
+worker/frontend/mcp), and that overlap plus the per-worker cost tipped a
16 GB box with no swap into the OOM killer on 10 Sep (see
documentation/plans/deploy/PLAN-deploy-memory-and-ci-speed.md).

Why post_fork disposes the engine: `preload_app` means the SQLAlchemy engine
(app/database.py, a module-level connection pool) is created ONCE in the
master, before the fork. A forked child inherits the parent's pooled
connections as open file descriptors; if two processes then write to the same
underlying socket, Postgres sees interleaved, invalid protocol traffic. This
is SQLAlchemy's documented fork recipe: `engine.dispose(close=False)` drops
the parent's pooled connections from the child's copy of the pool WITHOUT
closing the parent's sockets (the parent is still using them), so each
worker lazily opens its own fresh connections on first use.

Not needed for the RQ redis connection pool (app/services/queue_service.py,
also module-level): redis-py's ConnectionPool tracks the PID that created it
and resets itself (drops any inherited connections) the first time a forked
child tries to use it (`ConnectionPool._checkpid`), and the pool is empty at
import time regardless (redis-py connects lazily on first command, not at
construction) - so there is nothing for post_fork to dispose here.

Rollback without a rebuild: set GUNICORN_PRELOAD=0 in
sorento_crm_backend/.env and recreate the colour - every worker goes back to
importing the app independently, exactly as before this file existed. Note
this is a REBUILD-time toggle only: with preload_app on, a `kill -HUP` on the
master respawns workers from the app already imported in the master's
memory, so a code change needs the colour recreated (new container), not a
SIGHUP.
"""
import os

preload_app = os.environ.get("GUNICORN_PRELOAD", "1") != "0"

workers = int(os.environ.get("WORKERS", "4"))
worker_class = "uvicorn.workers.UvicornWorker"

_api_host = os.environ.get("API_HOST", "0.0.0.0")
_api_port = os.environ.get("API_PORT", "8000")
bind = f"{_api_host}:{_api_port}"

timeout = 120
# Must be LONGER than the host nginx's upstream keepalive (its
# keepalive_timeout, default 60s / 75s). With 5s gunicorn closed idle
# upstream connections that nginx still considered open, and the next
# request on that socket died as an intermittent 502 "upstream prematurely
# closed connection" - about 1 in 25 of the ESB's 14s ingest batches on
# production, 2026-09-07, which their all-or-nothing push then amplified
# into a 5x re-offer rate.
keepalive = int(os.environ.get("GUNICORN_KEEP_ALIVE", "75"))

accesslog = "-"
errorlog = "-"
loglevel = "info"


def post_fork(server, worker):
    """Runs in each forked worker, immediately after the fork.

    Only matters under preload_app: with it off, every worker imports the app
    (and app.database.engine) fresh, so there is nothing inherited to drop.
    """
    from app.database import engine

    engine.dispose(close=False)
