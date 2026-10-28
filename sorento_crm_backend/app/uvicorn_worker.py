"""The gunicorn worker class (gunicorn.conf.py `worker_class`): uvicorn's own, with a bounded
graceful shutdown.

CHAT-INBOX-QUEUE (IQ-28): without `timeout_graceful_shutdown` uvicorn waits for EVERY open
connection before the lifespan shutdown runs, and a staff event stream never closes, so the
app's shutdown handler (which lets the inbox drains finish their row) was never reached
before gunicorn's SIGKILL. 100 s lets a sync mode-off `/chat/turn` (n8n's 90 s budget)
finish; the budget against `graceful_timeout` is written out in
`app/tasks/chat_turns.py` (INBOX_SHUTDOWN_GRACE_SECONDS).

BACKEND-MEMORY: a worker also retires on its own (gunicorn `max_requests`, or a `TTOU`), and
`DrainingServer` makes that shutdown as graceful as a deploy's stop.
"""
from __future__ import annotations

import sys
import threading
import time
from typing import Callable

from gunicorn.arbiter import Arbiter
from uvicorn import Config, Server
from uvicorn.workers import UvicornWorker

TIMEOUT_GRACEFUL_SHUTDOWN_SECONDS = 100


class DrainingServer(Server):
    """uvicorn's server, closing two gaps a self-retiring worker hits:

    - uvicorn's request limit (gunicorn `max_requests`) ends the main loop with no signal, so the
      inbox drains, which stop taking rows at SIGTERM, kept taking them for the whole connection
      wait; shutdown now stops them first, whatever started it.
    - gunicorn's heartbeat is sent only from uvicorn's main loop (`Server.on_tick`), so through the
      shutdown (up to 148 s, app/tasks/chat_turns.py) the arbiter heard nothing and aborted the
      worker after its `timeout` (120 s), mid-row. A thread keeps beating until the shutdown
      returns, never past `heartbeat_for` (gunicorn's graceful_timeout), so a hung shutdown is
      still killed. A thread, because the lifespan shutdown blocks the event loop."""

    HEARTBEAT_EVERY = 5.0

    def __init__(self, config: Config, notify: Callable[[], None], heartbeat_for: float) -> None:
        super().__init__(config=config)
        self._notify = notify
        self._heartbeat_for = heartbeat_for

    async def shutdown(self, sockets=None) -> None:
        from app.tasks import chat_turns

        chat_turns.begin_inbox_shutdown()
        done = threading.Event()
        threading.Thread(target=self._beat, args=(done,), name="gunicorn-heartbeat", daemon=True).start()
        try:
            await super().shutdown(sockets)
        finally:
            done.set()

    def _beat(self, done: threading.Event) -> None:
        deadline = time.monotonic() + self._heartbeat_for
        while time.monotonic() < deadline:
            self._notify()
            if done.wait(min(self.HEARTBEAT_EVERY, max(0.0, deadline - time.monotonic()))):
                return


class InboxUvicornWorker(UvicornWorker):
    CONFIG_KWARGS = {**UvicornWorker.CONFIG_KWARGS, "timeout_graceful_shutdown": TIMEOUT_GRACEFUL_SHUTDOWN_SECONDS}

    async def _serve(self) -> None:
        # uvicorn's own `_serve`, with DrainingServer in place of Server.
        self.config.app = self.wsgi
        server = DrainingServer(self.config, self.notify, self.cfg.graceful_timeout)
        self._install_sigquit_handler()
        await server.serve(sockets=self.sockets)
        if not server.started:
            sys.exit(Arbiter.WORKER_BOOT_ERROR)
