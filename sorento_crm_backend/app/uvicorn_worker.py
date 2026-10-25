"""The gunicorn worker class (gunicorn.conf.py `worker_class`): uvicorn's own, with a bounded
graceful shutdown.

CHAT-INBOX-QUEUE (IQ-28): without `timeout_graceful_shutdown` uvicorn waits for EVERY open
connection before the lifespan shutdown runs, and a staff event stream never closes, so the
app's shutdown handler (which lets the inbox drains finish their row) was never reached
before gunicorn's SIGKILL. 100 s lets a sync mode-off `/chat/turn` (n8n's 90 s budget)
finish; the budget against `graceful_timeout` is written out in
`app/tasks/chat_turns.py` (INBOX_SHUTDOWN_GRACE_SECONDS).
"""
from __future__ import annotations

from uvicorn.workers import UvicornWorker

TIMEOUT_GRACEFUL_SHUTDOWN_SECONDS = 100


class InboxUvicornWorker(UvicornWorker):
    CONFIG_KWARGS = {**UvicornWorker.CONFIG_KWARGS, "timeout_graceful_shutdown": TIMEOUT_GRACEFUL_SHUTDOWN_SECONDS}
